"""Tests for the product price-history API (GET /api/products/{id}/history). Phase 8, 8.B1.

Auth-gated, per-user (DB-R1): a product the caller does not own is a 404. History rows are seeded
through the Catalog Update Service on the app's engine (each price change appends one entry).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient

PLUGIN = "dragon_store"


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _admin_token(client: TestClient) -> str:
    login = client.post("/api/auth/login", json={"username": "admin", "password": "initpass123"})
    access = login.json()["access_token"]
    client.post(
        "/api/auth/change-password",
        json={"new_password": "adminpass123"},
        headers=_bearer(access),
    )
    relogin = client.post("/api/auth/login", json={"username": "admin", "password": "adminpass123"})
    return str(relogin.json()["access_token"])


def _make_user(client: TestClient, admin_token: str, username: str) -> tuple[int, str]:
    """Create a user, clear the forced password change, return (id, access token)."""
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
        "/api/auth/change-password",
        json={"new_password": "userpass123"},
        headers=_bearer(access),
    )
    relogin = client.post("/api/auth/login", json={"username": username, "password": "userpass123"})
    return uid, str(relogin.json()["access_token"])


def _seed(user_id: int, *, price: str, available: bool = True) -> None:
    from src.core.catalog import update_catalog
    from src.core.contracts import Product
    from src.core.db import new_session

    product = Product(
        plugin_id=PLUGIN,
        external_id="x",
        url="https://example.com/p.gp.1.uw",
        name="Item",
        image_url=None,
        price_current=Decimal(price),
        price_original=Decimal(price),
        discount_pct=None,
        currency="EUR",
        is_available=available,
        scraped_at=datetime.now(UTC),
        extra={},
    )
    session = new_session()
    try:
        update_catalog(session, user_id, PLUGIN, [product])
    finally:
        session.close()


def _first_product_id(client: TestClient, token: str) -> int:
    return int(client.get("/api/catalog", headers=_bearer(token)).json()["items"][0]["id"])


def test_history_requires_auth(client: TestClient) -> None:
    assert client.get("/api/products/1/history").status_code == 401


def test_missing_product_is_404(client: TestClient) -> None:
    _uid, token = _make_user(client, _admin_token(client), "alice@example.com")
    resp = client.get("/api/products/999/history", headers=_bearer(token))
    assert resp.status_code == 404
    assert resp.json()["code"] == "product_not_found"


def test_other_users_product_is_404(client: TestClient) -> None:
    admin = _admin_token(client)
    alice_uid, alice = _make_user(client, admin, "alice@example.com")
    _bob_uid, bob = _make_user(client, admin, "bob@example.com")
    _seed(alice_uid, price="10.00")
    pid = _first_product_id(client, alice)

    # Bob owns nothing; Alice's product must be invisible to him (DB-R1).
    assert client.get(f"/api/products/{pid}/history", headers=_bearer(bob)).status_code == 404


def test_returns_stepped_series(client: TestClient) -> None:
    uid, token = _make_user(client, _admin_token(client), "alice@example.com")
    _seed(uid, price="10.00")  # first sight → one history entry
    _seed(uid, price="8.00")  # price change → a second entry
    pid = _first_product_id(client, token)

    resp = client.get(f"/api/products/{pid}/history?range=all", headers=_bearer(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["product_id"] == pid
    assert body["range"] == "all"
    prices = [p["price"] for p in body["points"]]
    assert prices == ["10.00", "8.00"]  # ordered oldest → newest
    assert all(isinstance(p["price"], str) for p in body["points"])  # Decimal as JSON string
    assert all(isinstance(p["available"], bool) for p in body["points"])


def test_bad_range_is_rejected(client: TestClient) -> None:
    # An out-of-enum range is a validation error; this app renders it as 400 (the {detail,code}
    # envelope, BE-11) rather than FastAPI's default 422.
    uid, token = _make_user(client, _admin_token(client), "alice@example.com")
    _seed(uid, price="10.00")
    pid = _first_product_id(client, token)
    bad = client.get(f"/api/products/{pid}/history?range=nope", headers=_bearer(token))
    assert bad.status_code == 400
