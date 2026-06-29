"""Tests for the carts CRUD API (phase 5.B1).

Auth-gated, per-user (DB-R1). ``mode`` is fixed at creation (CART-R2) and a
scraper_specific cart must name a loaded scraper (dragon_store is loaded in the
test app); cross carts must not. Membership + computed state arrive in 5.B2/5.B3.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


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


def _make_user(client: TestClient, admin_token: str, username: str) -> str:
    client.post(
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
    login = client.post("/api/auth/login", json={"username": username, "password": "temp-pass-123"})
    access = login.json()["access_token"]
    client.post(
        "/api/auth/change-password",
        json={"new_password": "userpass123"},
        headers=_bearer(access),
    )
    relogin = client.post("/api/auth/login", json={"username": username, "password": "userpass123"})
    return str(relogin.json()["access_token"])


def test_carts_require_auth(client: TestClient) -> None:
    assert client.get("/api/carts").status_code == 401


def test_cross_cart_crud_cycle(client: TestClient) -> None:
    token = _make_user(client, _admin_token(client), "alice")

    created = client.post(
        "/api/carts", json={"name": "Camera", "mode": "cross"}, headers=_bearer(token)
    )
    assert created.status_code == 201
    cart = created.json()
    assert cart["mode"] == "cross"
    assert cart["scraper_id"] is None
    assert cart["member_count"] == 0
    cart_id = cart["id"]

    listed = client.get("/api/carts", headers=_bearer(token)).json()
    assert [c["id"] for c in listed] == [cart_id]

    renamed = client.patch(
        f"/api/carts/{cart_id}", json={"name": "Mirrorless camera"}, headers=_bearer(token)
    )
    assert renamed.json()["name"] == "Mirrorless camera"

    assert client.delete(f"/api/carts/{cart_id}", headers=_bearer(token)).status_code == 204
    assert client.get("/api/carts", headers=_bearer(token)).json() == []


def test_scraper_specific_requires_a_loaded_scraper(client: TestClient) -> None:
    token = _make_user(client, _admin_token(client), "alice")

    ok = client.post(
        "/api/carts",
        json={"name": "Wishlist", "mode": "scraper_specific", "scraper_id": "dragon_store"},
        headers=_bearer(token),
    )
    assert ok.status_code == 201
    assert ok.json()["scraper_id"] == "dragon_store"

    missing = client.post(
        "/api/carts", json={"name": "x", "mode": "scraper_specific"}, headers=_bearer(token)
    )
    assert missing.status_code == 422
    assert missing.json()["code"] == "scraper_id_required"

    unknown = client.post(
        "/api/carts",
        json={"name": "x", "mode": "scraper_specific", "scraper_id": "nope"},
        headers=_bearer(token),
    )
    assert unknown.status_code == 422
    assert unknown.json()["code"] == "unknown_scraper"


def test_cross_cart_rejects_scraper_id(client: TestClient) -> None:
    token = _make_user(client, _admin_token(client), "alice")
    resp = client.post(
        "/api/carts",
        json={"name": "x", "mode": "cross", "scraper_id": "dragon_store"},
        headers=_bearer(token),
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "scraper_id_not_allowed"


def test_carts_are_per_user(client: TestClient) -> None:
    admin = _admin_token(client)
    token_a = _make_user(client, admin, "alice")
    token_b = _make_user(client, admin, "bob")

    cart_id = client.post(
        "/api/carts", json={"name": "Alice cart", "mode": "cross"}, headers=_bearer(token_a)
    ).json()["id"]

    assert client.get("/api/carts", headers=_bearer(token_b)).json() == []
    assert client.get(f"/api/carts/{cart_id}", headers=_bearer(token_b)).status_code == 404
    assert client.delete(f"/api/carts/{cart_id}", headers=_bearer(token_b)).status_code == 404
