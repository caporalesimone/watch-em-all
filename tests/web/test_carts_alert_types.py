"""Tests for the per-cart alert types API (phase 6.B1).

``PUT /api/carts/{id}/alert-types`` replaces the enabled set (presence = enabled,
full-set semantics); values are validated against the AlertType enum; empty clears.
Auth-gated and per-user (DB-R1). The baseline lifecycle (seed/delete) is 6.B2/6.B3.
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


def _make_cart(client: TestClient, token: str) -> int:
    created = client.post(
        "/api/carts", json={"name": "Camera", "mode": "cross"}, headers=_bearer(token)
    )
    return int(created.json()["id"])


def test_alert_types_require_auth(client: TestClient) -> None:
    assert client.put("/api/carts/1/alert-types", json={"alert_types": []}).status_code == 401


def test_set_replaces_and_persists(client: TestClient) -> None:
    token = _make_user(client, _admin_token(client), "alice")
    cart_id = _make_cart(client, token)

    # A fresh cart has no alert types.
    assert client.get(f"/api/carts/{cart_id}", headers=_bearer(token)).json()["alert_types"] == []

    # Enable a set — persisted, returned sorted.
    resp = client.put(
        f"/api/carts/{cart_id}/alert-types",
        json={"alert_types": ["CART_THRESHOLD_REACHED", "PRODUCT_ON_SALE"]},
        headers=_bearer(token),
    )
    assert resp.status_code == 200
    assert resp.json()["alert_types"] == ["CART_THRESHOLD_REACHED", "PRODUCT_ON_SALE"]
    got = client.get(f"/api/carts/{cart_id}", headers=_bearer(token)).json()
    assert got["alert_types"] == ["CART_THRESHOLD_REACHED", "PRODUCT_ON_SALE"]

    # Full-set semantics: a new set replaces the old one entirely.
    client.put(
        f"/api/carts/{cart_id}/alert-types",
        json={"alert_types": ["PRODUCT_UNAVAILABLE"]},
        headers=_bearer(token),
    )
    assert client.get(f"/api/carts/{cart_id}", headers=_bearer(token)).json()["alert_types"] == [
        "PRODUCT_UNAVAILABLE"
    ]

    # Idempotent + de-duplicated.
    dup = client.put(
        f"/api/carts/{cart_id}/alert-types",
        json={"alert_types": ["PRODUCT_ON_SALE", "PRODUCT_ON_SALE"]},
        headers=_bearer(token),
    )
    assert dup.json()["alert_types"] == ["PRODUCT_ON_SALE"]

    # Empty clears them all.
    cleared = client.put(
        f"/api/carts/{cart_id}/alert-types", json={"alert_types": []}, headers=_bearer(token)
    )
    assert cleared.json()["alert_types"] == []


def test_unknown_alert_type_rejected(client: TestClient) -> None:
    token = _make_user(client, _admin_token(client), "alice")
    cart_id = _make_cart(client, token)
    resp = client.put(
        f"/api/carts/{cart_id}/alert-types",
        json={"alert_types": ["PRODUCT_ON_SALE", "NOT_A_TYPE"]},
        headers=_bearer(token),
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "unknown_alert_type"
    # Rejected as a batch: nothing was persisted.
    assert client.get(f"/api/carts/{cart_id}", headers=_bearer(token)).json()["alert_types"] == []


def test_alert_types_are_per_user(client: TestClient) -> None:
    admin = _admin_token(client)
    token_a = _make_user(client, admin, "alice")
    token_b = _make_user(client, admin, "bob")
    cart_id = _make_cart(client, token_a)

    resp = client.put(
        f"/api/carts/{cart_id}/alert-types",
        json={"alert_types": ["PRODUCT_ON_SALE"]},
        headers=_bearer(token_b),
    )
    assert resp.status_code == 404
