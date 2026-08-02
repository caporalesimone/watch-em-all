"""Tests for the cart price-history API (GET /api/carts/{id}/history). Phase 8, 8.B2.

Auth-gated, per-user (DB-R1). The series is the stepped sum of the cart's current members'
own series, projecting the current composition onto the past (HIST-R4).
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


def _seed(user_id: int, *products: dict[str, object]) -> None:
    from src.core.catalog import update_catalog
    from src.core.contracts import Product
    from src.core.db import new_session

    items = []
    for over in products:
        base: dict[str, object] = {
            "plugin_id": PLUGIN,
            "external_id": "x",
            "url": "https://example.com/p.gp.1.uw",
            "name": "Item",
            "image_url": None,
            "price_current": Decimal("10.00"),
            "price_original": Decimal("10.00"),
            "discount_pct": None,
            "currency": "EUR",
            "is_available": True,
            "scraped_at": datetime.now(UTC),
            "extra": {},
        }
        base.update(over)
        items.append(Product(**base))  # type: ignore[arg-type]
    session = new_session()
    try:
        update_catalog(session, user_id, PLUGIN, items)
    finally:
        session.close()


def _cross_cart(client: TestClient, token: str) -> int:
    return int(
        client.post(
            "/api/carts", json={"name": "C", "mode": "cross"}, headers=_bearer(token)
        ).json()["id"]
    )


def _ids(client: TestClient, token: str) -> list[int]:
    body = client.get("/api/catalog?page_size=100", headers=_bearer(token)).json()
    return [int(i["id"]) for i in body["items"]]


def test_history_requires_auth(client: TestClient) -> None:
    assert client.get("/api/carts/1/history").status_code == 401


def test_missing_cart_is_404(client: TestClient) -> None:
    _uid, token = _make_user(client, _admin_token(client), "alice@example.com")
    resp = client.get("/api/carts/999/history", headers=_bearer(token))
    assert resp.status_code == 404


def test_other_users_cart_is_404(client: TestClient) -> None:
    admin = _admin_token(client)
    _a_uid, alice = _make_user(client, admin, "alice@example.com")
    _b_uid, bob = _make_user(client, admin, "bob@example.com")
    cart = _cross_cart(client, alice)
    assert client.get(f"/api/carts/{cart}/history", headers=_bearer(bob)).status_code == 404


def test_empty_cart_has_no_points(client: TestClient) -> None:
    _uid, token = _make_user(client, _admin_token(client), "alice@example.com")
    cart = _cross_cart(client, token)
    resp = client.get(f"/api/carts/{cart}/history", headers=_bearer(token))
    assert resp.status_code == 200
    assert resp.json()["points"] == []


def test_total_is_the_sum_of_members(client: TestClient) -> None:
    uid, token = _make_user(client, _admin_token(client), "alice@example.com")
    # Both in ONE batch: a second update_catalog would delist whatever is absent from it.
    _seed(
        uid,
        {"external_id": "a", "price_current": Decimal("10.00")},
        {"external_id": "b", "price_current": Decimal("20.00")},
    )
    cart = _cross_cart(client, token)
    client.post(
        f"/api/carts/{cart}/items",
        json={"product_ids": _ids(client, token)},
        headers=_bearer(token),
    )

    body = client.get(f"/api/carts/{cart}/history?range=all", headers=_bearer(token)).json()
    assert body["cart_id"] == cart
    assert body["range"] == "all"
    assert body["points"]
    # Both members available → the most recent total is their sum.
    assert body["points"][-1]["total"] == "30.00"
    assert all(isinstance(p["total"], str) for p in body["points"])
