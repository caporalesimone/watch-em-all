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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast

from fastapi import FastAPI
from fastapi.testclient import TestClient

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


def _make_user(client: TestClient, admin_token: str, username: str) -> tuple[int, str]:
    resp = client.post(
        "/api/admin/users",
        json={
            "username": username,
            "first_name": "Test",
            "last_name": "User",
            "role": "user",
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
        created = client.post(f"{DS}/watches", json={"url": url}, headers=h)
    assert created.status_code == 201
    watch_id = created.json()["id"]
    assert created.json()["url"] == url
    assert created.json()["kind"] == "product"
    # the scraper resolved the product title on add (shown instead of the URL)
    assert "Cthulhu" in created.json()["name"]
    assert len(created.json()["category"]) >= 1  # snapshot includes the category

    listed = client.get(f"{DS}/watches", headers=h).json()
    assert [w["url"] for w in listed] == [url]
    assert "Cthulhu" in listed[0]["name"]

    assert client.delete(f"{DS}/watches/{watch_id}", headers=h).status_code == 204
    assert client.get(f"{DS}/watches", headers=h).json() == []


def test_watches_are_per_user(client: TestClient) -> None:
    admin = _admin_token(client)
    _uid_a, ta = _make_user(client, admin, "alice")
    _uid_b, tb = _make_user(client, admin, "bob")
    with DragonServer() as base:
        client.post(f"{DS}/watches", json={"url": gp_url(base, "896")}, headers=_bearer(ta))
    assert client.get(f"{DS}/watches", headers=_bearer(tb)).json() == []


def test_add_duplicate_watch_rejected(client: TestClient) -> None:
    _uid, token = _user(client)
    h = _bearer(token)
    with DragonServer() as base:
        url = gp_url(base, "896")
        assert client.post(f"{DS}/watches", json={"url": url}, headers=h).status_code == 201
        dup = client.post(f"{DS}/watches", json={"url": url}, headers=h)
    assert dup.status_code == 409
    assert dup.json()["code"] == "duplicate_watch"
    assert len(client.get(f"{DS}/watches", headers=h).json()) == 1  # still one


# --- HTTP: dry-run (real scrape, no write) ---


def test_dry_run_discounted_sanitises_title_and_writes_nothing(client: TestClient) -> None:
    _uid, token = _user(client)
    h = _bearer(token)
    with DragonServer() as base:
        resp = client.post(f"{DS}/test", json={"url": gp_url(base, "896")}, headers=h)
    assert resp.status_code == 200
    products = resp.json()
    assert len(products) == 1
    product = products[0]
    assert product["plugin_id"] == "dragon_store"
    assert product["price_current"] == "9.90"
    assert product["currency"] == "EUR"
    assert product["is_available"] is True
    assert product["brand"]["text"] == "Giochi Uniti"
    # title label stripped from the name and surfaced as a tag
    assert "OFFERTA RAVEN PRIME" not in product["name"].upper()
    assert "Offerta Raven Prime" in product["tags"]
    # nothing persisted (dry-run)
    assert client.get("/api/catalog", headers=h).json()["total"] == 0


def test_dry_run_preorder_tags_pre_order_and_is_available(client: TestClient) -> None:
    _uid, token = _user(client)
    h = _bearer(token)
    with DragonServer() as base:
        resp = client.post(f"{DS}/test", json={"url": gp_url(base, "36099")}, headers=h)
    product = resp.json()[0]
    assert product["is_available"] is True  # PreOrder is orderable
    assert "Pre Order" in product["tags"]


def test_dry_run_out_of_stock_is_unavailable(client: TestClient) -> None:
    _uid, token = _user(client)
    h = _bearer(token)
    with DragonServer() as base:
        resp = client.post(f"{DS}/test", json={"url": gp_url(base, "27006")}, headers=h)
    product = resp.json()[0]
    assert product["is_available"] is False


# --- HTTP: scrape-now + cooldown ---


def test_scrape_now_populates_catalog(client: TestClient) -> None:
    _uid, token = _user(client)
    h = _bearer(token)
    with DragonServer() as base:
        client.post(f"{DS}/watches", json={"url": gp_url(base, "896")}, headers=h)
        started = client.post(f"{DS}/scrape-now", headers=h)
        assert started.status_code == 202
        assert started.json()["status"] == "started"
        page = client.get("/api/catalog", headers=h).json()

    assert page["total"] == 1
    assert page["items"][0]["plugin_id"] == "dragon_store"


def test_scrape_now_cooldown_blocks_second(client: TestClient) -> None:
    _uid, token = _user(client)
    h = _bearer(token)
    with DragonServer() as base:
        client.post(f"{DS}/watches", json={"url": gp_url(base, "896")}, headers=h)
        assert client.post(f"{DS}/scrape-now", headers=h).status_code == 202
        blocked = client.post(f"{DS}/scrape-now", headers=h)
    assert blocked.status_code == 429
    assert blocked.json()["code"] == "scrape_cooldown"

    status = client.get(f"{DS}/scrape-now", headers=h).json()
    assert status["available"] is False
    assert status["retry_after_seconds"] > 0
    assert status["interval_seconds"] == 3600


def test_scrape_now_status_available_before_first_run(client: TestClient) -> None:
    _uid, token = _user(client)
    status = client.get(f"{DS}/scrape-now", headers=_bearer(token)).json()
    assert status["available"] is True
    assert status["available_at"] is None


def test_scrape_now_cooldown_interval_follows_admin_config(client: TestClient) -> None:
    # The per-scraper reserved config (scrape_now_min_interval_s, 4.B10) drives the cooldown
    # the GET status reports (the UI countdown); a short interval reflects on the next read.
    _uid, token = _user(client)
    h = _bearer(token)
    session = new_session()
    try:
        set_scraper_config(session, "dragon_store", {"scrape_now_min_interval_s": 30})
    finally:
        session.close()
    with DragonServer() as base:
        client.post(f"{DS}/watches", json={"url": gp_url(base, "896")}, headers=h)
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
        client.post(f"{DS}/watches", json={"url": gp_url(base, "896")}, headers=_bearer(token))
        first = _run_for_user(client, uid)
        second = _run_for_user(client, uid)

    assert first.new == 1
    assert second.new == 0  # same product, stable identity -> no duplicate
    assert second.price_changes == 0  # unchanged price -> no spurious history


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
        client.post(f"{DS}/watches", json={"url": gp_url(base, "896")}, headers=h)
        client.post(f"{DS}/watches", json={"url": gp_url(base, "896") + "?ref=promo"}, headers=h)
        counters = _run_for_user(client, uid)
    assert counters.found == 1  # deduped on external_id


def test_run_for_user_brand_and_price_persisted(client: TestClient) -> None:
    uid, token = _user(client)
    h = _bearer(token)
    with DragonServer() as base:
        client.post(f"{DS}/watches", json={"url": gp_url(base, "34602")}, headers=h)
        counters = _run_for_user(client, uid)
        page = client.get("/api/catalog", headers=h).json()
    assert counters.new == 1
    assert page["total"] == 1
    item = page["items"][0]
    assert item["price_current"] == "89.99"  # full price
    assert item["is_available"] is True
    assert item["brand"]["text"] == "Raven Distribution"
    assert "Edizione Limitata" in item["tags"]  # tag surfaced via the API
    assert "EDIZIONE LIMITATA" not in item["name"].upper()  # label stripped from the name
    assert len(item["category"]) >= 1  # category breadcrumb persisted (PROD-R7)
