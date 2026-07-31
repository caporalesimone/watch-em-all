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
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from src.core.db import new_session
from src.core.http import HttpClient
from src.core.models import CatalogProduct
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
    local server; returns the delta counters. **No scrape cache**, so every page in
    these tests is a real fetch and request counting means what it says."""
    lp = _dragon(client)
    ctx = build_context(lp.manifest, lp.plugin)
    ctx.http = HttpClient(min_interval_s=0.0, sleep=lambda _s: None)
    try:
        return lp.plugin.run_for_user(ctx, uid)
    finally:
        ctx.db.close()


def _run_for_user_cached(client: TestClient, uid: int):  # type: ignore[no-untyped-def]
    """A run through the **production** HTTP wiring, scrape cache included.

    `build_context` builds that client itself, so this is just the run with nothing swapped
    out; the suite's fixture neutralises the politeness wait on the class, so it is still
    fast. Needed to test what a cached page does to `last_seen_at` and the per-product
    statistics — the one thing a cacheless client cannot show."""
    lp = _dragon(client)
    ctx = build_context(lp.manifest, lp.plugin)
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

    ``priced_details`` re-points one card's **detail** page at a fixture that does carry a
    price. Both priceless cards of the real page turn out to be free, so with the shipped
    fixtures a run that reads their detail pages and a run that throws those reads away land
    the same catalog — which is how the bug in 9.B2b's tail pass stayed invisible.

    ``unreadable`` makes those listing pages answer **404** while page one still announces the
    full count: a walk that stops halfway, which is not the same failure as a site that is
    gone — page one delivered, and the row has to say how far it got.
    """

    def __init__(
        self,
        *,
        paginated: bool = False,
        priced_details: dict[str, str] | None = None,
        unreadable: set[int] | None = None,
    ) -> None:
        cthulhu = (_FIX / "sp_192_cthulhu_one_page.html").read_bytes()
        page1 = (_FIX / "sp_115_classici_page1.html").read_bytes()
        page2 = (_FIX / "sp_115_classici_page2.html").read_bytes()
        if paginated:
            page1 = page1.replace(b"50 per pagina - 21 in totale", b"50 per pagina - 2 in totale")
            page2 = page2.replace(b"50 per pagina - 21 in totale", b"50 per pagina - 2 in totale")
        listing = {1: page1, 2: page2} if paginated else {1: cthulhu}
        for page in unreadable or ():
            listing.pop(page, None)
        details = {
            gid: (_FIX / name).read_bytes()
            for gid, name in {
                **_FIXTURES,
                "28079": "gp_28079_free_no_price.html",
                # The other priceless card of that page; we hold no capture of its own page, and
                # a page with no price is exactly what it needs to be for this test.
                "22992": "gp_28079_free_no_price.html",
                "14415": "gp_14415_unavailable_no_price.html",
                **(priced_details or {}),
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


def _set_include_dented(client: TestClient, headers: dict[str, str], value: bool) -> Any:
    """Flip the dented filter the way the page does (9.F1): through the API, on the user's only
    watch. It used to write the column directly, which tested the walk and not the route."""
    watch_id = client.get(f"{DS}/watches", headers=headers).json()[0]["id"]
    return client.patch(
        f"{DS}/watches/{watch_id}", json={"include_ammaccati": value}, headers=headers
    )


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
        assert _set_include_dented(client, h, True).json()["include_ammaccati"] is True
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


def test_adding_a_category_keeps_the_prices_its_tail_pass_settled(client: TestClient) -> None:
    """C2: `_resolve_unpriced` writes into the dict it is given, and on the add path that dict
    was built inline and thrown away — so the detail pages were fetched, politeness wait
    included, and their prices went nowhere.

    22992 is a card the listing shows with no price at all; here its detail page carries one.
    Without the fix it lands at 0,00 with a Free tag, which is what an actual free download
    looks like — a 9,90 product filed as free, and a price-drop alert waiting to happen.
    """
    _uid, token = _user(client)
    h = _bearer(token)
    with CategoryServer(priced_details={"22992": "gp_896_discounted.html"}) as base:
        _add_watch(client, h, sp_url(base))  # the add only: no scheduled run to repair it

    items = client.get("/api/catalog", params={"page_size": 100}, headers=h).json()["items"]
    (settled,) = [i for i in items if ".gp.22992.uw" in i["url"]]
    assert settled["price_current"] == "9.90"
    assert "Free" not in settled["tags"]
    # The genuinely priceless one is still free: the tail pass decides per product, and
    # "no price on the detail page either" is the case that legitimately means zero.
    (free,) = [i for i in items if ".gp.28079.uw" in i["url"]]
    assert (free["price_current"], "Free" in free["tags"]) == ("0.00", True)


def test_a_listing_served_from_the_cache_does_not_pretend_the_site_just_answered(
    client: TestClient,
) -> None:
    """C3/PROD-R8: `last_seen_at` is when the **site** answered, and a page replayed from the
    scrape cache carries the timestamp of the fetch that filled it.

    The walk used to discard that timestamp, so fifty products off a twelve-hour-old page were
    all dated "now" — the field whose entire job is to say how fresh this is, reporting when we
    last re-served a listing. The same timestamp decides `observations` vs `cache_hits`, so both
    per-product counters were wrong by construction on a category.

    A live response carries no timestamp (a real fetch *is* now, give or take milliseconds), so
    the assertion on the second read is that the field did not move **forward**: it is
    re-stamped with the cache entry's own, marginally earlier, instant.
    """
    uid, token = _user(client)
    h = _bearer(token)
    with CategoryServer() as base:
        _add_watch(client, h, sp_url(base))  # a real fetch, which fills the scrape cache
        first_seen, observations, cache_hits = _seen_and_counters(uid)
        _run_for_user_cached(client, uid)  # same page, served from the cache this time
        second_seen, observations_after, cache_hits_after = _seen_and_counters(uid)

    assert (observations, cache_hits) == (1, 0)
    # The replay counted as a replay, and did not date the product to now.
    assert (observations_after, cache_hits_after) == (1, 1)
    assert second_seen <= first_seen


class UnreadableServer:
    """A site that answers **200** with something that is not a product page at all: no
    JSON-LD, no anti-bot gate, no error banner of its own. That is a parse failure — our
    reading broke — as opposed to the site telling us, inside a 200, that it has no such page.
    """

    def __init__(self) -> None:
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=iso-8859-1")
                self.end_headers()
                self.wfile.write(b"<html><body><h1>Benvenuto</h1></body></html>")

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


def test_a_product_page_that_will_not_parse_is_counted_like_a_listing_that_will_not(
    client: TestClient,
) -> None:
    """C6/9.B6c: `parse_failures_total` was bumped on a listing and never on a product page, so
    the statistic could not show the breakage we have actually had — a page shape that stopped
    parsing. `scrape_run` has retention; this counter is the only memory of "since when".
    """
    _uid, token = _user(client)
    h = _bearer(token)
    before = _parse_failures()
    with UnreadableServer() as base:
        added = _add_watch(client, h, gp_url(base, "896"))
        row = _wait_resolved(client, h)[0]

    assert added.status_code == 201  # the watch is kept: unreadable now is not gone
    assert row["status"] == "failed"
    assert _parse_failures() - before == 1


def _parse_failures() -> int:
    from src.core.scraper_stats import get_stats

    session = new_session()
    try:
        return int(get_stats(session, "dragon_store").parse_failures_total)
    finally:
        session.close()


def _seen_and_counters(uid: int) -> tuple[datetime, int, int]:
    """One product's `last_seen_at` and its two read counters. 36099 is on the listing page and
    is not one of the priceless cards, so it is only ever seen through the listing."""
    session = new_session()
    try:
        # By URL, not by external_id: that one is a hash of the identity seed.
        row = session.scalars(
            select(CatalogProduct).where(
                CatalogProduct.user_id == uid, CatalogProduct.url.like("%gp.36099.uw%")
            )
        ).one()
        return row.last_seen_at, row.observations, row.cache_hits
    finally:
        session.close()


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


# --- where a product comes from (C14) ---


def _sources_of(client: TestClient, headers: dict[str, str], marker: str) -> list[tuple[str, str]]:
    items = client.get("/api/catalog", params={"page_size": 100}, headers=headers).json()["items"]
    (found,) = [i for i in items if marker in i["url"]]
    return [(s["kind"], s["label"]) for s in found["sources"]]


def test_the_catalog_says_which_input_delivers_a_product(client: TestClient) -> None:
    """C14: the deletion confirmation has to answer "will this come back?" with a fact instead
    of a conditional, and it can only do that if the delivery said where the product came from.
    The label is the category's name, not its URL — it is shown to a user."""
    uid, token = _user(client)
    h = _bearer(token)
    with CategoryServer() as base:
        _add_watch(client, h, sp_url(base))
        _run_for_user(client, uid)

    assert _sources_of(client, h, ".gp.36099.uw") == [("category", "Il Richiamo di Cthulhu")]


def test_a_product_watched_twice_over_names_both_inputs(client: TestClient) -> None:
    """Why this is many-to-many and not a foreign key (9.B4): removing the category would not
    stop this product coming back, because it is also watched on its own."""
    uid, token = _user(client)
    h = _bearer(token)
    with CategoryServer() as base:
        _add_watch(client, h, f"{base}/prod.1.1.1.gp.36099.uw")
        _add_watch(client, h, sp_url(base))
        _run_for_user(client, uid)

    sources = dict(_sources_of(client, h, ".gp.36099.uw"))
    assert set(sources) == {"product", "category"}
    assert sources["category"] == "Il Richiamo di Cthulhu"


def test_removing_an_input_stops_its_products_claiming_it(client: TestClient) -> None:
    """The products stay — removing a watch has never removed what it found — but they stop
    promising a return that nothing will cause any more."""
    uid, token = _user(client)
    h = _bearer(token)
    with CategoryServer() as base:
        _add_watch(client, h, sp_url(base))
        _run_for_user(client, uid)
    assert _sources_of(client, h, ".gp.36099.uw") == [("category", "Il Richiamo di Cthulhu")]

    (watch,) = client.get(f"{DS}/watches", headers=h).json()
    assert client.delete(f"{DS}/watches/{watch['id']}", headers=h).status_code == 204

    assert client.get("/api/catalog", headers=h).json()["total"] == 38  # still theirs
    assert _sources_of(client, h, ".gp.36099.uw") == []


# --- what the page needs to describe a watch (9.F1/9.F2/9.F3) ---


def test_the_backend_says_what_a_pasted_url_is(client: TestClient) -> None:
    """9.F2: the page asks while the user is still pasting, so it can offer the dented toggle
    for a category and not for a product. Answered here rather than by a second copy of the
    URL grammar in TypeScript."""
    _uid, token = _user(client)
    h = _bearer(token)

    def kind_of(url: str) -> Any:
        return client.get(f"{DS}/classify", params={"url": url}, headers=h).json()["kind"]

    assert kind_of("https://dragonstore.it/x.1.1.1.gp.35880.uw") == "product"
    assert kind_of("https://dragonstore.it/cthulhu.1.1.192.sp.uw?idA=19") == "category"
    assert kind_of("https://dragonstore.it/chi-siamo.asp") is None
    assert kind_of("not a url at all") is None
    # Unauthenticated it answers nothing, like every other route of this plugin.
    assert client.get(f"{DS}/classify", params={"url": "https://x/y.gp.1.uw"}).status_code == 401


def test_a_category_can_be_added_with_dented_items_included(client: TestClient) -> None:
    """9.F2: the toggle is part of the add, not something to fix up afterwards — the first walk
    is the expensive one, and doing it twice to change one flag is what we are avoiding."""
    uid, token = _user(client)
    h = _bearer(token)
    with CategoryServer() as base:
        created = client.post(
            f"{DS}/watches",
            json={"url": sp_url(base), "include_ammaccati": True},
            headers=h,
        )
        assert created.status_code == 201
        assert created.json()["include_ammaccati"] is True
        _wait_resolved(client, h)
        _run_for_user(client, uid)

    page = client.get("/api/catalog", params={"page_size": 100}, headers=h).json()
    assert page["total"] == 39  # nothing was left out
    assert any("Ammaccato" in i["tags"] for i in page["items"])


def test_a_product_watch_never_carries_the_dented_filter(client: TestClient) -> None:
    """DRG-R7: the filter is a property of a listing. Asked for on a single product it would
    mean refusing the very page the user pasted, so it is dropped, and the toggle that sends it
    is not even offered."""
    _uid, token = _user(client)
    h = _bearer(token)
    with DragonServer() as base:
        created = client.post(
            f"{DS}/watches",
            json={"url": gp_url(base, "896"), "include_ammaccati": True},
            headers=h,
        )
        _wait_resolved(client, h)
    assert created.json()["include_ammaccati"] is False

    # And it cannot be turned on later either: there is nothing for it to filter.
    refused = _set_include_dented(client, h, True)
    assert refused.status_code == 422
    assert refused.json()["code"] == "not_a_category"


def test_a_watch_reports_what_its_last_scan_took(client: TestClient) -> None:
    """9.F1/9.F3: the counters are what the list and the add-outcome panel read. They are a
    photograph of the scan, written on the row — not a count of the catalog, which several
    watches can contribute to at once."""
    uid, token = _user(client)
    h = _bearer(token)
    with CategoryServer() as base:
        _add_watch(client, h, sp_url(base))
        _run_for_user(client, uid)

    (watch,) = client.get(f"{DS}/watches", headers=h).json()
    assert watch["kind"] == "category"
    assert watch["products_included"] == 38
    assert watch["products_excluded"] == 1  # the dented listing the default filter left out
    assert watch["last_scanned_at"] is not None
    # And it is called what the site calls it: a listing URL is unreadable in a list (9.F1).
    assert watch["name"] == "Il Richiamo di Cthulhu"
    assert [c["text"] for c in watch["category"]] == ["Giochi di Ruolo", "GDR Italiano"]


def test_the_dented_filter_cannot_be_changed_mid_scan(client: TestClient) -> None:
    """The walk reads that column between pages: a change landing halfway through would apply
    to the second half of a category and not the first.

    The drainer is stopped so the row stays in flight for the length of the assertion —
    otherwise the test measures that race instead of the rule (same reason as the queue tests).
    """
    from src.plugins.scrapers.dragon_store.backend import Watch
    from src.web.jobs import stop_drainers

    stop_drainers()
    # One admin token for both users: taking a second one would log in with a password the
    # first call already changed.
    admin = _admin_token(client)
    uid, token = _make_user(client, admin, "alice")
    h = _bearer(token)
    session = new_session()
    try:
        row = Watch(user_id=uid, kind="category", url="https://x/c.1.1.1.sp.uw", status="running")
        session.add(row)
        session.commit()
        watch_id = row.id
    finally:
        session.close()

    busy = client.patch(f"{DS}/watches/{watch_id}", json={"include_ammaccati": True}, headers=h)
    assert busy.status_code == 409
    assert busy.json()["code"] == "watch_busy"

    # Somebody else's watch is not found, never forbidden — that would confirm it exists.
    _uid_b, token_b = _make_user(client, admin, "bob")
    other = client.patch(
        f"{DS}/watches/{watch_id}", json={"include_ammaccati": True}, headers=_bearer(token_b)
    )
    assert other.status_code == 404


# --- what a run over a category reports (DoD: idempotency + coherent counters) ---


def test_a_second_run_over_a_category_changes_nothing(client: TestClient) -> None:
    """The phase's Definition of Done, and the one place a dedup or delisting mistake would
    show as thirty-eight rows instead of one: run the same category twice with the site
    unchanged and every delta has to be zero — including ``removed``, which is the dangerous
    one, since the second delivery is complete and therefore *allowed* to delist."""
    uid, token = _user(client)
    h = _bearer(token)
    with CategoryServer() as base:
        _add_watch(client, h, sp_url(base))
        first = _run_for_user(client, uid)
        second = _run_for_user(client, uid)
        third = _run_for_user(client, uid)  # a third, because "stable" is not "stable once"

    assert first.found == second.found == third.found == 38
    # Adding the watch already stored the products, so even the first run is an update.
    assert (first.new, second.new, third.new) == (0, 0, 0)
    assert (first.price_changes, second.price_changes, third.price_changes) == (0, 0, 0)
    assert (first.removed, second.removed, third.removed) == (0, 0, 0)
    assert client.get("/api/catalog", headers=h).json()["total"] == 38

    # The other half of "nothing changed": the per-product statistics of 9.B6b. Every row was
    # observed at least once and none recorded a price move — and there are 38 rows, not 38
    # times three, which is what a broken identity would look like.
    session = new_session()
    try:
        rows = session.scalars(select(CatalogProduct).where(CatalogProduct.user_id == uid)).all()
        assert len(rows) == 38
        assert {r.price_changes for r in rows} == {0}
        assert {r.availability_changes for r in rows} == {0}
        assert all(r.observations >= 1 for r in rows)
        assert not any(r.removed for r in rows)
    finally:
        session.close()


def test_a_run_reports_what_the_dented_filter_left_out(client: TestClient) -> None:
    """`scrape_run.products_excluded` has existed since 4.B6 and nothing ever wrote it: a run
    over a category of 39 reported 38 found and left the missing one unexplained. Only the
    plugin can say — the catalog service is handed the survivors."""
    admin = _admin_token(client)  # taken once: it changes the admin's own password
    uid, token = _make_user(client, admin, "alice")
    h = _bearer(token)
    with CategoryServer() as base:
        _add_watch(client, h, sp_url(base))
        delta = _run_for_user(client, uid)

    assert delta.found == 38
    assert delta.excluded == 1  # the dented listing on that page

    # A single product excludes nothing, and must not inherit the count.
    uid_b, token_b = _make_user(client, admin, "bob")
    with DragonServer() as base:
        _add_watch(client, _bearer(token_b), gp_url(base, "896"))
        assert _run_for_user(client, uid_b).excluded == 0


def test_a_category_walk_counts_its_pages_in_the_lifetime_statistics(client: TestClient) -> None:
    """9.B6c: `scrape_run` has retention, so the per-scraper row is the only memory of what
    this scraper has ever done. A page read is where the time goes — eleven seconds of
    politeness each — so it is counted per page, not per product."""
    uid, token = _user(client)
    h = _bearer(token)
    server = CategoryServer(paginated=True)
    with server as base:
        _add_watch(client, h, sp_url(base))
        before = _pages_fetched(client)
        _run_for_user(client, uid)
        after = _pages_fetched(client)

    # Two listing pages in this run (the add read them too, which is what `before` absorbs).
    assert after - before == 2
    assert sum("pg=2" in c for c in server.listing_calls()) >= 1


def _pages_fetched(client: TestClient) -> int:
    from src.core.scraper_stats import get_stats

    session = new_session()
    try:
        return int(get_stats(session, "dragon_store").pages_fetched_total)
    finally:
        session.close()


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


def test_a_walk_stopped_by_an_unreadable_page_records_the_pages_it_read(
    client: TestClient,
) -> None:
    """C20: progress is counted in **requests**, so a walk that stopped early has to say so.

    The terminal transition used to fill the bar to its total unconditionally, so a category
    that broke on page 2 of 2 left "2 of 2 read" on the row — next to a `status_detail` saying
    some pages could not be read. Two fields of the same row contradicting each other, and the
    contract (DRG-R2, features.md) promises the count of pages read.
    """
    _uid, token = _user(client)
    h = _bearer(token)
    with CategoryServer(paginated=True, unreadable={2}) as base:
        _add_watch(client, h, sp_url(base))

    row = client.get(f"{DS}/watches", headers=h).json()[0]
    assert (row["progress_done"], row["progress_total"]) == (1, 2)
    # Page one delivered, so the watch is usable; the detail is what says it is not whole.
    assert row["status"] == "ready"
    assert "could not be read" in (row["status_detail"] or "")


def test_a_resolved_product_records_the_one_request_it_costs(client: TestClient) -> None:
    """The other half of C20: nothing counts steps on the single-product path, so the step is
    recorded where it happens. Inferring it at the end is what made the category lie."""
    _uid, token = _user(client)
    h = _bearer(token)
    with DragonServer() as base:
        _add_watch(client, h, gp_url(base, "896"))

    row = client.get(f"{DS}/watches", headers=h).json()[0]
    assert (row["progress_done"], row["progress_total"]) == (1, 1)
