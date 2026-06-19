"""Tests for the Dragon Store scraper (phase-3 MOCK) and the scrape-now flow.

HTTP tests drive the real app (watches CRUD, dry-run, scrape-now cooldown). The
``run_for_user`` mock (idempotency, no-watch, identity dedup) is exercised by
calling the loaded plugin directly with a real context — the plugin is reached
through ``app.state.loaded_plugins`` to avoid importing the plugin package.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.core.plugins.context import build_context

DS = "/api/plugins/dragon-store"
URL_A = "https://shop.example/il-richiamo.1.1.192.gp.35880.uw"
URL_B = "https://shop.example/altro.1.1.192.gp.41000.uw"


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


def _dragon(client: TestClient):  # type: ignore[no-untyped-def]
    return next(lp for lp in client.app.state.loaded_plugins if lp.manifest.name == "dragon_store")


# --- HTTP: watches CRUD ---


def test_watches_crud(client: TestClient) -> None:
    _uid, token = _user(client)
    h = _bearer(token)

    assert client.get(f"{DS}/watches", headers=h).json() == []

    created = client.post(f"{DS}/watches", json={"url": URL_A}, headers=h)
    assert created.status_code == 201
    watch_id = created.json()["id"]
    assert created.json()["url"] == URL_A
    assert created.json()["kind"] == "product"

    listed = client.get(f"{DS}/watches", headers=h).json()
    assert [w["url"] for w in listed] == [URL_A]

    assert client.delete(f"{DS}/watches/{watch_id}", headers=h).status_code == 204
    assert client.get(f"{DS}/watches", headers=h).json() == []


def test_watches_are_per_user(client: TestClient) -> None:
    admin = _admin_token(client)
    _uid_a, ta = _make_user(client, admin, "alice")
    _uid_b, tb = _make_user(client, admin, "bob")
    client.post(f"{DS}/watches", json={"url": URL_A}, headers=_bearer(ta))
    assert client.get(f"{DS}/watches", headers=_bearer(tb)).json() == []


# --- HTTP: dry-run (no write) ---


def test_dry_run_returns_products_without_writing(client: TestClient) -> None:
    _uid, token = _user(client)
    h = _bearer(token)
    resp = client.post(f"{DS}/test", json={"url": URL_A}, headers=h)
    assert resp.status_code == 200
    products = resp.json()
    assert len(products) == 1
    assert products[0]["plugin_id"] == "dragon_store"
    assert "MOCK" in products[0]["name"]
    # nothing persisted
    assert client.get("/api/catalog", headers=h).json()["total"] == 0


# --- HTTP: scrape-now + cooldown ---


def test_scrape_now_populates_catalog(client: TestClient) -> None:
    _uid, token = _user(client)
    h = _bearer(token)
    client.post(f"{DS}/watches", json={"url": URL_A}, headers=h)

    started = client.post(f"{DS}/scrape-now", headers=h)
    assert started.status_code == 202
    assert started.json()["status"] == "started"

    page = client.get("/api/catalog", headers=h).json()
    assert page["total"] == 1
    assert page["items"][0]["plugin_id"] == "dragon_store"


def test_scrape_now_cooldown_blocks_second(client: TestClient) -> None:
    _uid, token = _user(client)
    h = _bearer(token)
    client.post(f"{DS}/watches", json={"url": URL_A}, headers=h)

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


# --- direct: run_for_user mock (idempotency, no-watch, identity dedup) ---


def test_run_for_user_idempotent(client: TestClient) -> None:
    uid, token = _user(client)
    client.post(f"{DS}/watches", json={"url": URL_A}, headers=_bearer(token))
    lp = _dragon(client)

    ctx = build_context(lp.manifest, lp.plugin)
    try:
        first = lp.plugin.run_for_user(ctx, uid)
    finally:
        ctx.db.close()
    ctx2 = build_context(lp.manifest, lp.plugin)
    try:
        second = lp.plugin.run_for_user(ctx2, uid)
    finally:
        ctx2.db.close()

    assert first.new == 1
    assert second.new == 0  # same product, stable identity -> no duplicate
    assert second.price_changes == 0  # deterministic price -> no spurious history


def test_run_for_user_no_watches_writes_nothing(client: TestClient) -> None:
    uid, _token = _user(client)
    lp = _dragon(client)
    ctx = build_context(lp.manifest, lp.plugin)
    try:
        counters = lp.plugin.run_for_user(ctx, uid)
    finally:
        ctx.db.close()
    assert counters.found == 0
    assert counters.new == 0
    assert counters.removed == 0  # no watches must NOT delist


def test_identity_dedup_same_gp_id(client: TestClient) -> None:
    uid, token = _user(client)
    h = _bearer(token)
    # Two watches, same native gp id but different volatile URL -> one product.
    client.post(f"{DS}/watches", json={"url": URL_A}, headers=h)
    client.post(f"{DS}/watches", json={"url": URL_A + "?ref=promo"}, headers=h)
    lp = _dragon(client)
    ctx = build_context(lp.manifest, lp.plugin)
    try:
        counters = lp.plugin.run_for_user(ctx, uid)
    finally:
        ctx.db.close()
    assert counters.found == 1  # deduped on external_id
