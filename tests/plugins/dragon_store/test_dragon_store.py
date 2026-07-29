"""Tests for the Dragon Store scraper (real scraping) and the scrape-now flow.

Content-dependent tests run against a **local mock server** that serves the saved
fixtures by native gp id, so the watches point at ``http://127.0.0.1:.../...gp.<id>.uw``
and the real parser/sanitiser path is exercised end-to-end without the internet.
Watches CRUD and the cooldown status need no scraping. The plugin is reached
through ``app.state.loaded_plugins`` to avoid importing the plugin package.
"""

from __future__ import annotations

import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from src.core.db import new_session
from src.core.http import HttpClient
from src.core.plugins.context import build_context
from src.core.scraper_config import set_scraper_config

DS = "/api/plugins/dragon-store"

_FIX = Path(__file__).parent / "fixtures"
_FIXTURES = {
    "896": "gp_896_discounted.html",
    "36099": "gp_36099_preorder.html",
    "27006": "gp_27006_out_of_stock.html",
    "34602": "gp_34602_limited_edition.html",
    "30708": "gp_30708_other_category.html",
}
_GP_RE = re.compile(r"\.gp\.(\d+)\.uw")


def _wait_resolved(client: TestClient, headers: dict[str, str], *, count: int = 1) -> list[Any]:
    """Wait for the queued jobs to reach a terminal state (9.X6c).

    Adding a watch no longer resolves it inside the request: the row is queued and this
    scraper's drainer picks it up. Tests therefore have to wait for the same thing the page
    waits for. Woken by a poke, so this is milliseconds — the timeout only guards against a
    genuinely stuck drainer.
    """
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        rows = client.get(f"{DS}/watches", headers=headers).json()
        if len(rows) >= count and all(r["status"] not in ("queued", "running") for r in rows):
            return cast(list[Any], rows)
        time.sleep(0.01)
    raise AssertionError(
        f"jobs did not finish: {client.get(f'{DS}/watches', headers=headers).json()}"
    )


def _add_watch(client: TestClient, headers: dict[str, str], url: str) -> Any:
    """Add a watch and wait for its job to finish — what a user experiences as "added".

    Since 9.X6b/c the POST only enqueues: the row comes back `queued` and this scraper's
    drainer resolves it, holding the run lock while it does. Every test that goes on to touch
    the same scraper (a manual scrape, a run, the catalog) has to wait for that, so the wait
    lives here rather than in each test, where forgetting it makes the test flaky, not wrong.
    """
    added = client.post(f"{DS}/watches", json={"url": url}, headers=headers)
    if added.status_code == 201:
        _wait_resolved(
            client, headers, count=len(client.get(f"{DS}/watches", headers=headers).json())
        )
    return added


class DragonServer:
    """Serves the saved fixtures by gp id, on an ephemeral port; a context manager."""

    def __init__(self) -> None:
        pages = {gid: (_FIX / name).read_bytes() for gid, name in _FIXTURES.items()}

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                match = _GP_RE.search(self.path)
                body = pages.get(match.group(1)) if match else None
                if body is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=iso-8859-1")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, fmt: str, *args: Any) -> None:
                return

        self._srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._srv.serve_forever, daemon=True)

    def __enter__(self) -> str:
        self._thread.start()
        return f"http://127.0.0.1:{self._srv.server_address[1]}"

    def __exit__(self, *exc: object) -> None:
        self._srv.shutdown()
        self._srv.server_close()
        self._thread.join(timeout=2)


def gp_url(base: str, gp_id: str) -> str:
    return f"{base}/prod.1.1.1.gp.{gp_id}.uw"


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _admin_token(client: TestClient) -> str:
    login = client.post("/api/auth/login", json={"username": "admin", "password": "initpass123"})
    access = login.json()["access_token"]
    client.post(
        "/api/auth/change-password", json={"new_password": "adminpass123"}, headers=_bearer(access)
    )
    relogin = client.post("/api/auth/login", json={"username": "admin", "password": "adminpass123"})
    return str(relogin.json()["access_token"])


def _make_user(
    client: TestClient, admin_token: str, username: str, role: str = "user"
) -> tuple[int, str]:
    resp = client.post(
        "/api/admin/users",
        json={
            "username": username,
            "first_name": "Test",
            "last_name": "User",
            "role": role,
            "temp_password": "temp-pass-123",
        },
        headers=_bearer(admin_token),
    )
    uid = int(resp.json()["id"])
    login = client.post("/api/auth/login", json={"username": username, "password": "temp-pass-123"})
    access = login.json()["access_token"]
    client.post(
        "/api/auth/change-password", json={"new_password": "userpass123"}, headers=_bearer(access)
    )
    relogin = client.post("/api/auth/login", json={"username": username, "password": "userpass123"})
    return uid, str(relogin.json()["access_token"])


def _user(client: TestClient, username: str = "alice") -> tuple[int, str]:
    return _make_user(client, _admin_token(client), username)


def _super_user(client: TestClient, username: str = "sudo") -> tuple[int, str]:
    """A super-user, which is what the manual scrape now needs (9.B8). A plain user does not
    get it at all — the restriction is the API's, not a hidden button's."""
    return _make_user(client, _admin_token(client), username, role="super_user")


def _dragon(client: TestClient):  # type: ignore[no-untyped-def]  # test helper: returns the loaded plugin
    app = cast(FastAPI, client.app)
    return next(lp for lp in app.state.loaded_plugins if lp.manifest.name == "dragon_store")


def _run_for_user(client: TestClient, uid: int):  # type: ignore[no-untyped-def]
    """Run the loaded plugin with a fast (no-politeness) HTTP client against the
    local server; returns the delta counters."""
    lp = _dragon(client)
    ctx = build_context(lp.manifest, lp.plugin)
    ctx.http = HttpClient(min_interval_s=0.0, sleep=lambda _s: None)
    try:
        return lp.plugin.run_for_user(ctx, uid)
    finally:
        ctx.db.close()


# --- HTTP: watches CRUD (no scraping) ---


def test_watches_crud(client: TestClient) -> None:
    _uid, token = _user(client)
    h = _bearer(token)

    assert client.get(f"{DS}/watches", headers=h).json() == []

    with DragonServer() as base:
        url = gp_url(base, "896")
        created = _add_watch(client, h, url)
        # The drainer resolves it after the response; the mock server has to still be up.
        listed = _wait_resolved(client, h)
    assert created.status_code == 201
    watch_id = created.json()["id"]
    assert created.json()["url"] == url
    assert created.json()["kind"] == "product"
    # The answer comes back before the scrape does (9.X6b): the row is the job, and it
    # starts out queued with nothing resolved yet.
    assert created.json()["status"] == "queued"
    assert created.json()["name"] is None

    # The list reads the row, not the page's memory, so it shows the finished state.
    assert [w["url"] for w in listed] == [url]
    assert listed[0]["status"] == "ready"
    assert "Cthulhu" in listed[0]["name"]
    assert len(listed[0]["category"]) >= 1  # snapshot includes the category

    assert client.delete(f"{DS}/watches/{watch_id}", headers=h).status_code == 204
    assert client.get(f"{DS}/watches", headers=h).json() == []


def test_watches_are_per_user(client: TestClient) -> None:
    admin = _admin_token(client)
    _uid_a, ta = _make_user(client, admin, "alice")
    _uid_b, tb = _make_user(client, admin, "bob")
    with DragonServer() as base:
        _add_watch(client, _bearer(ta), gp_url(base, "896"))
    assert client.get(f"{DS}/watches", headers=_bearer(tb)).json() == []


def test_add_duplicate_watch_rejected(client: TestClient) -> None:
    _uid, token = _user(client)
    h = _bearer(token)
    with DragonServer() as base:
        url = gp_url(base, "896")
        assert _add_watch(client, h, url).status_code == 201
        dup = _add_watch(client, h, url)
    assert dup.status_code == 409
    assert dup.json()["code"] == "duplicate_watch"
    assert len(client.get(f"{DS}/watches", headers=h).json()) == 1  # still one


# --- HTTP: adding a watch scrapes and stores the product (0.8.1) ---
#
# These used to go through the dry-run route, removed in 0.9.0 along with the whole
# preview flow: adding a URL already scrapes it and writes it, so a second no-write
# scrape of the same page was a second round of requests for one intention. The
# parser coverage they carried is kept, now read back from the catalog.


def _added_product(client: TestClient, headers: dict[str, str], gp_id: str) -> dict[str, Any]:
    with DragonServer() as base:
        added = _add_watch(client, headers, gp_url(base, gp_id))
        _wait_resolved(client, headers)
    assert added.status_code == 201
    page = client.get("/api/catalog", headers=headers).json()
    assert page["total"] == 1
    return cast(dict[str, Any], page["items"][0])


def test_adding_a_watch_sanitises_the_title_and_stores_the_product(client: TestClient) -> None:
    _uid, token = _user(client)
    h = _bearer(token)
    product = _added_product(client, h, "896")
    assert product["plugin_id"] == "dragon_store"
    assert product["price_current"] == "9.90"
    assert product["currency"] == "EUR"
    assert product["is_available"] is True
    assert product["brand"]["text"] == "Giochi Uniti"
    # title label stripped from the name and surfaced as a tag
    assert "OFFERTA RAVEN PRIME" not in product["name"].upper()
    assert "Offerta Raven Prime" in product["tags"]


def test_preorder_tags_pre_order_and_is_available(client: TestClient) -> None:
    _uid, token = _user(client)
    product = _added_product(client, _bearer(token), "36099")
    assert product["is_available"] is True  # PreOrder is orderable
    assert "Pre Order" in product["tags"]


def test_out_of_stock_is_unavailable(client: TestClient) -> None:
    _uid, token = _user(client)
    product = _added_product(client, _bearer(token), "27006")
    assert product["is_available"] is False


# --- HTTP: scrape-now + cooldown ---


def test_scrape_now_populates_catalog(client: TestClient) -> None:
    _uid, token = _super_user(client)
    h = _bearer(token)
    with DragonServer() as base:
        _add_watch(client, h, gp_url(base, "896"))
        # The add holds this scraper's run lock while the queue resolves it (9.X6c), so a
        # manual scrape started right now is correctly refused with 409.
        _wait_resolved(client, h)
        started = client.post(f"{DS}/scrape-now", headers=h)
        assert started.status_code == 202
        assert started.json()["status"] == "started"
        page = client.get("/api/catalog", headers=h).json()

    assert page["total"] == 1
    assert page["items"][0]["plugin_id"] == "dragon_store"


def test_scrape_now_cooldown_blocks_second(client: TestClient) -> None:
    _uid, token = _super_user(client)
    h = _bearer(token)
    with DragonServer() as base:
        _add_watch(client, h, gp_url(base, "896"))
        # The add is a job now, and it holds this scraper's run lock while it resolves
        # (9.X6c): pressing Scrape now before it finishes is legitimately refused.
        _wait_resolved(client, h)
        assert client.post(f"{DS}/scrape-now", headers=h).status_code == 202
        blocked = client.post(f"{DS}/scrape-now", headers=h)
    assert blocked.status_code == 429
    assert blocked.json()["code"] == "scrape_cooldown"

    status = client.get(f"{DS}/scrape-now", headers=h).json()
    assert status["available"] is False
    assert status["retry_after_seconds"] > 0
    assert status["interval_seconds"] == 3600


def test_scrape_now_status_available_before_first_run(client: TestClient) -> None:
    _uid, token = _super_user(client)
    status = client.get(f"{DS}/scrape-now", headers=_bearer(token)).json()
    assert status["available"] is True
    assert status["available_at"] is None


def test_scrape_now_cooldown_interval_follows_admin_config(client: TestClient) -> None:
    # The per-scraper reserved config (scrape_now_min_interval_s, 4.B10) drives the cooldown
    # the GET status reports (the UI countdown); a short interval reflects on the next read.
    _uid, token = _super_user(client)
    h = _bearer(token)
    session = new_session()
    try:
        set_scraper_config(session, "dragon_store", {"scrape_now_min_interval_s": 30})
    finally:
        session.close()
    with DragonServer() as base:
        _add_watch(client, h, gp_url(base, "896"))
        # The add is a job now, and it holds this scraper's run lock while it resolves
        # (9.X6c): pressing Scrape now before it finishes is legitimately refused.
        _wait_resolved(client, h)
        assert client.post(f"{DS}/scrape-now", headers=h).status_code == 202
        blocked = client.post(f"{DS}/scrape-now", headers=h)
    assert blocked.status_code == 429
    status = client.get(f"{DS}/scrape-now", headers=h).json()
    assert status["interval_seconds"] == 30
    assert 0 < status["retry_after_seconds"] <= 30


# --- direct: run_for_user (idempotency, no-watch, identity dedup) ---


def test_run_for_user_idempotent(client: TestClient) -> None:
    uid, token = _user(client)
    with DragonServer() as base:
        _add_watch(client, _bearer(token), gp_url(base, "896"))
        _wait_resolved(client, _bearer(token))  # the add resolves in the queue (9.X6c)
        first = _run_for_user(client, uid)
        second = _run_for_user(client, uid)

    # Adding the watch already stored the product, so even the *first* run is an update:
    # stable identity, no duplicate, and no spurious history on an unchanged price.
    assert first.new == 0
    assert first.found == 1
    assert second.new == 0
    assert second.price_changes == 0


def test_run_for_user_no_watches_writes_nothing(client: TestClient) -> None:
    uid, _token = _user(client)
    counters = _run_for_user(client, uid)
    assert counters.found == 0
    assert counters.new == 0
    assert counters.removed == 0  # no watches must NOT delist


def test_identity_dedup_same_gp_id(client: TestClient) -> None:
    uid, token = _user(client)
    h = _bearer(token)
    with DragonServer() as base:
        # Two watches, same native gp id but different volatile URL -> one product.
        _add_watch(client, h, gp_url(base, "896"))
        _add_watch(client, h, gp_url(base, "896") + "?ref=promo")
        counters = _run_for_user(client, uid)
    assert counters.found == 1  # deduped on external_id


def test_run_for_user_brand_and_price_persisted(client: TestClient) -> None:
    uid, token = _user(client)
    h = _bearer(token)
    with DragonServer() as base:
        _add_watch(client, h, gp_url(base, "34602"))
        counters = _run_for_user(client, uid)
        page = client.get("/api/catalog", headers=h).json()
    assert counters.found == 1  # already inserted when the watch was added
    assert page["total"] == 1
    item = page["items"][0]
    assert item["price_current"] == "89.99"  # full price
    assert item["is_available"] is True
    assert item["brand"]["text"] == "Raven Distribution"
    assert "Edizione Limitata" in item["tags"]  # tag surfaced via the API
    assert "EDIZIONE LIMITATA" not in item["name"].upper()  # label stripped from the name
    assert len(item["category"]) >= 1  # category breadcrumb persisted (PROD-R7)


# --- the anti-bot interstitial and the soft rate limit (site change of 2026-07-25) ---

_CHALLENGE_BODY = (
    b"<!DOCTYPE html><html><head><title>Verifica accesso / Security Check</title></head>"
    b'<body><input type="checkbox" id="humanCheck">'
    b'<script>fetch("/ajaxRequests.asp?cmd=captcha_check_ok")</script></body></html>'
)
_SOFT_429_BODY = (
    b'<div id="pageNotFound"><p><strong>429</strong> <span>Too Many Requests</span>.</p></div>'
)


class GatedServer:
    """Dragon Store as it behaves since 2026-07-25: the interstitial until the clear
    endpoint is called, then the real fixtures. Everything is served with HTTP **200**,
    which is the whole difficulty. ``state`` is mutable so a test can make the site start
    rate-limiting halfway through.
    """

    def __init__(self, state: dict[str, bool] | None = None) -> None:
        pages = {gid: (_FIX / name).read_bytes() for gid, name in _FIXTURES.items()}
        self.state = state if state is not None else {"cleared": False, "rate_limited": False}
        self.calls: list[str] = []
        state_ref, calls = self.state, self.calls

        class Handler(BaseHTTPRequestHandler):
            def _send(self, status: int, body: bytes, ctype: str) -> None:
                self.send_response(status)
                self.send_header("Content-Type", ctype)
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:
                calls.append(self.path)
                if self.path == "/robots.txt":
                    self._send(200, b"User-agent: *\nCrawl-delay: 0\n", "text/plain")
                    return
                if "captcha_check_ok" in self.path:
                    state_ref["cleared"] = True
                    self._send(200, b"OK", "text/plain")
                    return
                if state_ref.get("rate_limited"):
                    self._send(200, _SOFT_429_BODY, "text/html")
                    return
                if not state_ref.get("cleared"):
                    self._send(200, _CHALLENGE_BODY, "text/html")
                    return
                match = _GP_RE.search(self.path)
                body = pages.get(match.group(1)) if match else None
                if body is None:
                    self._send(404, b"", "text/html")
                    return
                self._send(200, body, "text/html; charset=iso-8859-1")

            def log_message(self, fmt: str, *args: Any) -> None:
                return

        self._srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._srv.serve_forever, daemon=True)

    def __enter__(self) -> str:
        self._thread.start()
        return f"http://127.0.0.1:{self._srv.server_address[1]}"

    def __exit__(self, *exc: object) -> None:
        self._srv.shutdown()
        self._srv.server_close()
        self._thread.join(timeout=2)

    def gp_calls(self, since: int = 0) -> list[str]:
        return [c for c in self.calls[since:] if _GP_RE.search(c)]


def test_interstitial_is_cleared_once_and_the_page_retried(client: TestClient) -> None:
    uid, token = _user(client)
    h = _bearer(token)
    server = GatedServer()
    with server as base:
        added = _add_watch(client, h, gp_url(base, "896"))
        rows = _wait_resolved(client, h)

    assert added.status_code == 201
    # Resolved through the gate, not left as a bare URL — read from the row, since the
    # response is sent before the job runs (9.X6b/c).
    assert rows[0]["name"]
    assert sum("captcha_check_ok" in c for c in server.calls) == 1  # cleared exactly once
    assert len(server.gp_calls()) == 2  # the gated attempt, then the retry
    # And the product landed in the catalogue straight away.
    assert client.get("/api/catalog", headers=h).json()["total"] == 1


def test_rate_limit_aborts_the_run_and_never_delists(client: TestClient) -> None:
    """The failure that used to wipe a catalogue: every page fails, the delivery is empty,
    and the delisting sweep must not run."""
    uid, token = _user(client)
    h = _bearer(token)
    server = GatedServer({"cleared": True, "rate_limited": False})
    with server as base:
        _add_watch(client, h, gp_url(base, "896"))
        _add_watch(client, h, gp_url(base, "36099"))
        _wait_resolved(client, h, count=2)  # both adds go through the queue (9.X6c)
        assert client.get("/api/catalog", headers=h).json()["total"] == 2

        server.state["rate_limited"] = True
        mark = len(server.calls)
        counters = _run_for_user(client, uid)

    assert counters.found == 0
    assert counters.removed == 0  # nothing delisted: we could not read, that is not "gone"
    # Aborted at the first rate-limited page instead of walking the second watch.
    assert len(server.gp_calls(mark)) == 1
    assert client.get("/api/catalog", headers=h).json()["total"] == 2


def test_watch_survives_a_site_that_cannot_be_read(client: TestClient) -> None:
    uid, token = _user(client)
    h = _bearer(token)
    server = GatedServer({"cleared": True, "rate_limited": True})
    with server as base:
        added = _add_watch(client, h, gp_url(base, "896"))
        row = _wait_resolved(client, h)[0]

    assert added.status_code == 201  # the watch is kept even when nothing could be read
    assert added.json()["name"] is None
    assert client.get("/api/catalog", headers=h).json()["total"] == 0
    # And it says so, rather than sitting in "running" for ever: a job the page polls has
    # to reach a terminal state whatever happened (9.X6b).
    assert row["status"] == "failed"
    assert row["status_detail"]


def test_a_url_that_is_neither_a_product_nor_a_category_is_refused(client: TestClient) -> None:
    _uid, token = _user(client)
    h = _bearer(token)
    for url in ("", "https://www.dragonstore.it/", "https://x/raven.1.0.0.br.18.uw"):
        refused = _add_watch(client, h, url)
        assert refused.status_code == 422
        assert refused.json()["code"] == "invalid_url"
    assert client.get(f"{DS}/watches", headers=h).json() == []


# --- job queue (9.X6c) -----------------------------------------------------------------


def test_a_job_left_running_by_a_dead_process_is_reclaimed(client: TestClient) -> None:
    """Jobs live in the web process, so a row still marked running cannot be: it is what a
    restart left behind. Leaving it would be worse than a lost scrape — that state blocks the
    user's next submission, and a lock with no expiry shuts them out of their own plugin."""
    from src.plugins.scrapers.dragon_store.backend import Watch

    uid, token = _user(client)
    session = new_session()
    try:
        session.add(
            Watch(user_id=uid, kind="product", url="https://x/stuck.gp.1.uw", status="running")
        )
        session.commit()
    finally:
        session.close()

    lp = _dragon(client)
    ctx = build_context(lp.manifest, lp.plugin)
    try:
        assert lp.plugin.reclaim_orphan_jobs(ctx) == 1
    finally:
        ctx.db.close()

    row = client.get(f"{DS}/watches", headers=_bearer(token)).json()[0]
    assert row["status"] == "failed"
    assert "restart" in row["status_detail"]


def test_the_queue_reports_how_many_jobs_are_ahead(client: TestClient) -> None:
    """ "First in the queue" and "nothing is happening" have to be distinguishable, or a wait
    for the run lock reads as a fault (the ambiguity 9.X2 was about).

    The drainer is stopped first, deliberately: left running it empties the queue while the
    assertion is being read, and the test would measure that race instead of the arithmetic.
    A position only means anything while the job is still waiting.
    """
    from src.plugins.scrapers.dragon_store.backend import Watch
    from src.web.jobs import stop_drainers

    stop_drainers()
    uid, token = _user(client)
    session = new_session()
    try:
        for n in (1, 2, 3):
            session.add(
                Watch(user_id=uid, kind="product", url=f"https://x/q{n}.gp.{n}.uw", status="queued")
            )
        session.commit()
    finally:
        session.close()

    rows = client.get(f"{DS}/watches", headers=_bearer(token)).json()
    assert [r["queue_position"] for r in rows] == [0, 1, 2]


# --- job status and cancellation (9.X6d / 9.X6f) ----------------------------------------


def test_only_one_add_can_be_in_flight_per_user(client: TestClient) -> None:
    """The refusal has to come from the API, not the button: a disabled form stops nothing,
    and that state is exactly what a reload used to throw away (9.X6d)."""
    from src.plugins.scrapers.dragon_store.backend import Watch
    from src.web.jobs import stop_drainers

    stop_drainers()  # keep the first job in flight for the length of the assertion
    uid, token = _user(client)
    h = _bearer(token)
    session = new_session()
    try:
        session.add(Watch(user_id=uid, kind="product", url="https://x/a.gp.1.uw", status="running"))
        session.commit()
    finally:
        session.close()

    refused = client.post(f"{DS}/watches", json={"url": "https://x/b.gp.2.uw"}, headers=h)
    assert refused.status_code == 409
    assert refused.json()["code"] == "add_in_progress"


def test_the_job_endpoint_describes_what_is_happening(client: TestClient) -> None:
    from src.plugins.scrapers.dragon_store.backend import Watch
    from src.web.jobs import stop_drainers

    stop_drainers()
    uid, token = _user(client)
    h = _bearer(token)
    assert client.get(f"{DS}/watches/job", headers=h).json() == {
        "active": False,
        "watch_id": None,
        "kind": None,
        "url": None,
        "status": None,
        "status_detail": None,
        "progress_done": 0,
        "progress_total": None,
        "queue_position": 0,
        "cancellable": False,
    }

    session = new_session()
    try:
        session.add(
            Watch(
                user_id=uid,
                kind="category",
                url="https://x/c.sp.uw",
                status="running",
                progress_done=3,
                progress_total=21,
                status_detail="page 3 of 21",
            )
        )
        session.commit()
    finally:
        session.close()

    job = client.get(f"{DS}/watches/job", headers=h).json()
    assert job["active"] is True
    assert (job["progress_done"], job["progress_total"]) == (3, 21)
    assert job["status_detail"] == "page 3 of 21"
    assert job["cancellable"] is True  # a category can be stopped; a single product cannot


def test_cancelling_a_queued_job_stops_it_before_it_starts(client: TestClient) -> None:
    from src.plugins.scrapers.dragon_store.backend import Watch
    from src.web.jobs import stop_drainers

    stop_drainers()
    uid, token = _user(client)
    h = _bearer(token)
    session = new_session()
    try:
        watch = Watch(user_id=uid, kind="category", url="https://x/c.sp.uw", status="queued")
        session.add(watch)
        session.commit()
        watch_id = watch.id
    finally:
        session.close()

    accepted = client.post(f"{DS}/watches/{watch_id}/cancel", headers=h)
    assert accepted.status_code == 202
    assert accepted.json()["status"] == "cancelled"
    row = client.get(f"{DS}/watches", headers=h).json()[0]
    assert row["status"] == "cancelled"
    # The watch itself survives: the products a partial scrape wrote must keep something
    # delivering them, or the next complete run delists exactly those.
    assert row["url"] == "https://x/c.sp.uw"


def test_cancelling_something_that_is_not_running_is_refused(client: TestClient) -> None:
    from src.plugins.scrapers.dragon_store.backend import Watch
    from src.web.jobs import stop_drainers

    stop_drainers()
    uid, token = _user(client)
    h = _bearer(token)
    session = new_session()
    try:
        watch = Watch(user_id=uid, kind="product", url="https://x/d.gp.9.uw", status="ready")
        session.add(watch)
        session.commit()
        watch_id = watch.id
    finally:
        session.close()

    refused = client.post(f"{DS}/watches/{watch_id}/cancel", headers=h)
    assert refused.status_code == 409
    assert refused.json()["code"] == "not_running"


def test_a_running_job_stops_at_its_next_wait(client: TestClient) -> None:
    """Cancellation is cooperative and reaches into the politeness wait (9.X6f).

    Almost all of a scrape is that wait — 11 seconds a request, by the site's own request —
    so a flag only read between requests would feel broken. Here the wait is real (the
    fixture's neutralised sleep is bypassed by passing our own) and the job has to notice.
    """
    from src.plugins.scrapers.dragon_store.backend import Watch, _cancellable_sleep, _JobCancelled

    uid, _token = _user(client)
    session = new_session()
    try:
        watch = Watch(
            user_id=uid,
            kind="category",
            url="https://x/c.sp.uw",
            status="running",
            cancel_requested=True,
        )
        session.add(watch)
        session.commit()
        watch_id = watch.id
    finally:
        session.close()

    sleep = _cancellable_sleep(watch_id)
    started = time.monotonic()
    with pytest.raises(_JobCancelled):
        sleep(11.0)  # the real politeness interval
    assert time.monotonic() - started < 1.0  # gave up at once, not after eleven seconds


# --- categories end to end (9.B2/9.B2b/9.B3/9.B4/9.B5) ----------------------------------


class CategoryServer:
    """Serves the saved **listing** fixtures, plus the detail pages their cards link to.

    ``pg=N`` picks the page, the way the site does. The Cthulhu category is one real page and
    happens to contain every awkward case at once: a preorder, one dented listing and two
    products with no price. The two-page variant patches only the header of page 1 — the real
    one claims 21 pages and we hold 2 — so the walk stops where the fixtures end instead of
    re-reading page 2 nineteen times.
    """

    def __init__(self, *, paginated: bool = False) -> None:
        cthulhu = (_FIX / "sp_192_cthulhu_one_page.html").read_bytes()
        page1 = (_FIX / "sp_115_classici_page1.html").read_bytes()
        page2 = (_FIX / "sp_115_classici_page2.html").read_bytes()
        if paginated:
            page1 = page1.replace(b"50 per pagina - 21 in totale", b"50 per pagina - 2 in totale")
            page2 = page2.replace(b"50 per pagina - 21 in totale", b"50 per pagina - 2 in totale")
        listing = {1: page1, 2: page2} if paginated else {1: cthulhu}
        details = {
            gid: (_FIX / name).read_bytes()
            for gid, name in {
                **_FIXTURES,
                "28079": "gp_28079_free_no_price.html",
                # The other priceless card of that page; we hold no capture of its own page, and
                # a page with no price is exactly what it needs to be for this test.
                "22992": "gp_28079_free_no_price.html",
                "14415": "gp_14415_unavailable_no_price.html",
            }.items()
        }
        calls: list[str] = []
        self.calls = calls

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                calls.append(self.path)
                gp = _GP_RE.search(self.path)
                if ".sp.uw" in self.path:
                    found = re.search(r"[?&]pg=(\d+)", self.path)
                    body = listing.get(int(found.group(1)) if found else 1)
                elif gp is not None:
                    body = details.get(gp.group(1))
                else:
                    body = None
                if body is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=iso-8859-1")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, fmt: str, *args: Any) -> None:
                return

        self._srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._srv.serve_forever, daemon=True)

    def __enter__(self) -> str:
        self._thread.start()
        return f"http://127.0.0.1:{self._srv.server_address[1]}"

    def __exit__(self, *exc: object) -> None:
        self._srv.shutdown()
        self._srv.server_close()
        self._thread.join(timeout=2)

    def listing_calls(self) -> list[str]:
        return [c for c in self.calls if ".sp.uw" in c]


def sp_url(base: str) -> str:
    return f"{base}/cthulhu.1.1.192.sp.uw?idA=19"


def _set_include_dented(uid: int, value: bool) -> None:
    from src.plugins.scrapers.dragon_store.backend import Watch

    session = new_session()
    try:
        watch = session.scalars(select(Watch).where(Watch.user_id == uid)).one()
        watch.include_ammaccati = value
        session.commit()
    finally:
        session.close()


def test_a_category_watch_is_accepted_and_queued(client: TestClient) -> None:
    _uid, token = _user(client)
    h = _bearer(token)
    with CategoryServer() as base:
        created = client.post(f"{DS}/watches", json={"url": sp_url(base)}, headers=h)
        assert created.status_code == 201
        assert created.json()["kind"] == "category"
        # A category cannot know its size before page one; a product always costs one request.
        assert created.json()["progress_total"] is None
        _wait_resolved(client, h)


def test_a_category_fills_the_catalog_from_its_cards(client: TestClient) -> None:
    """The result the phase exists for: one URL, dozens of products, no request per product."""
    uid, token = _user(client)
    h = _bearer(token)
    with CategoryServer() as base:
        _add_watch(client, h, sp_url(base))
        counters = _run_for_user(client, uid)

    page = client.get("/api/catalog", headers=h).json()
    # 39 cards on the page, one of them dented and excluded by default (DRG-R4).
    assert page["total"] == 38
    assert counters.found == 38
    names = [item["name"] for item in page["items"]]
    assert not any("AMMACCATO" in n.upper() for n in names)
    # The breadcrumb of the listing page stands in for the one a card has not got.
    assert all(len(item["category"]) == 3 for item in page["items"])


def test_dented_listings_come_in_only_when_the_watch_asks(client: TestClient) -> None:
    uid, token = _user(client)
    h = _bearer(token)
    with CategoryServer() as base:
        _add_watch(client, h, sp_url(base))
        _set_include_dented(uid, True)
        _run_for_user(client, uid)

    page = client.get("/api/catalog", params={"page_size": 100}, headers=h).json()
    assert page["total"] == 39  # the dented one included this time
    # The label is stripped from the name and kept as a tag, so the title reads normally.
    dented = [i for i in page["items"] if "Ammaccato" in i["tags"]]
    assert len(dented) == 1
    assert "AMMACCATO" not in dented[0]["name"].upper()


def test_a_product_the_listing_cannot_price_is_settled_on_its_own_page(
    client: TestClient,
) -> None:
    """9.B2b: two cards on this page show no price. Neither may be guessed at — one is a free
    download, and treating the other kind as free would put a priced product in the catalog at
    zero and fire a price-drop alert on it."""
    uid, token = _user(client)
    h = _bearer(token)
    with CategoryServer() as base:
        _add_watch(client, h, sp_url(base))
        _run_for_user(client, uid)

    items = client.get("/api/catalog", headers=h).json()["items"]
    free = [i for i in items if "Free" in i["tags"]]
    assert len(free) == 2
    assert all(i["price_current"] == "0.00" for i in free)


def test_a_category_is_walked_page_by_page(client: TestClient) -> None:
    uid, token = _user(client)
    h = _bearer(token)
    server = CategoryServer(paginated=True)
    with server as base:
        _add_watch(client, h, sp_url(base))
        _run_for_user(client, uid)

    # Two pages, read once each, with the second asked for by the site's own &pg=2.
    listing = server.listing_calls()
    assert sum("pg=2" in c for c in listing) >= 1
    # 50 + 50 cards, minus the 13 dented listings on page 1 that the watch did not ask for.
    assert client.get("/api/catalog", headers=h).json()["total"] == 87


def test_a_single_watch_covered_by_a_category_costs_no_extra_request(client: TestClient) -> None:
    """DRG-R3 and the reason the order is what it is (9.B4): the card and the detail page yield
    the same external_id, so a product a category already delivered needs no request of its own.
    """
    uid, token = _user(client)
    h = _bearer(token)
    server = CategoryServer()
    with server as base:
        # 36099 is on that listing page; watch it on its own as well.
        _add_watch(client, h, f"{base}/prod.1.1.1.gp.36099.uw")
        _add_watch(client, h, sp_url(base))
        mark = len(server.calls)
        _run_for_user(client, uid)
        gp_calls = [c for c in server.calls[mark:] if ".gp.36099.uw" in c]

    assert gp_calls == []  # the category already delivered it
    assert client.get("/api/catalog", headers=h).json()["total"] == 38


def test_a_category_page_that_cannot_be_read_never_delists(client: TestClient) -> None:
    """A half-read category is a partial delivery (CATSVC-R2b): "we could not read page 2" is
    not "those products are gone". This is the failure that used to wipe a catalogue."""
    uid, token = _user(client)
    h = _bearer(token)
    server = CategoryServer(paginated=True)
    with server as base:
        _add_watch(client, h, sp_url(base))
        _run_for_user(client, uid)
        before = client.get("/api/catalog", headers=h).json()["total"]

    # The site is gone now: the next run reads nothing at all.
    counters = _run_for_user(client, uid)
    assert counters.removed == 0
    assert client.get("/api/catalog", headers=h).json()["total"] == before
