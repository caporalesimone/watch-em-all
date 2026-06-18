"""Tests for admin user management: create + list, admin-only (user-management.md)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _admin_token(client: TestClient) -> str:
    # The bootstrap admin starts with a forced password change; clear it, then log
    # in again to get a token past the must-change gate that require_admin enforces.
    login = client.post("/api/auth/login", json={"username": "admin", "password": "initpass123"})
    access = login.json()["access_token"]
    client.post(
        "/api/auth/change-password",
        json={"new_password": "adminpass123"},
        headers=_bearer(access),
    )
    relogin = client.post("/api/auth/login", json={"username": "admin", "password": "adminpass123"})
    return str(relogin.json()["access_token"])


def _payload(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "username": "alice",
        "first_name": "Alice",
        "last_name": "Rossi",
        "role": "user",
        "temp_password": "temp-pass-123",
    }
    base.update(over)
    return base


def test_create_user_then_list(client: TestClient) -> None:
    token = _admin_token(client)
    resp = client.post("/api/admin/users", json=_payload(), headers=_bearer(token))
    assert resp.status_code == 201
    created = resp.json()
    assert created["username"] == "alice"
    assert created["role"] == "user"
    assert created["must_change_password"] is True
    assert created["last_login_at"] is None

    listed = client.get("/api/admin/users", headers=_bearer(token)).json()
    assert {u["username"] for u in listed} == {"admin", "alice"}


def test_created_user_can_log_in(client: TestClient) -> None:
    token = _admin_token(client)
    client.post("/api/admin/users", json=_payload(), headers=_bearer(token))
    # The new user logs in with the temporary password and is forced to change it.
    login = client.post("/api/auth/login", json={"username": "alice", "password": "temp-pass-123"})
    assert login.status_code == 200
    me = client.get("/api/me", headers=_bearer(login.json()["access_token"]))
    assert me.status_code == 200
    assert me.json()["must_change_password"] is True


def test_duplicate_username_rejected(client: TestClient) -> None:
    token = _admin_token(client)
    client.post("/api/admin/users", json=_payload(), headers=_bearer(token))
    dup = client.post("/api/admin/users", json=_payload(), headers=_bearer(token))
    assert dup.status_code == 409
    assert dup.json()["code"] == "username_taken"


def test_create_validations(client: TestClient) -> None:
    token = _admin_token(client)
    assert (
        client.post("/api/admin/users", json=_payload(last_name=""), headers=_bearer(token))
    ).status_code == 400
    assert (
        client.post(
            "/api/admin/users", json=_payload(temp_password="short"), headers=_bearer(token)
        )
    ).status_code == 400
    assert (
        client.post("/api/admin/users", json=_payload(role="superadmin"), headers=_bearer(token))
    ).status_code == 400


def test_requires_admin(client: TestClient) -> None:
    # No token → 401.
    assert client.get("/api/admin/users").status_code == 401
    assert client.post("/api/admin/users", json=_payload()).status_code == 401
    # A non-admin user → 403.
    admin = _admin_token(client)
    client.post("/api/admin/users", json=_payload(), headers=_bearer(admin))
    login = client.post("/api/auth/login", json={"username": "alice", "password": "temp-pass-123"})
    access = login.json()["access_token"]
    client.post(
        "/api/auth/change-password",
        json={"new_password": "alice-pass-123"},
        headers=_bearer(access),
    )
    relogin = client.post(
        "/api/auth/login", json={"username": "alice", "password": "alice-pass-123"}
    )
    user_token = str(relogin.json()["access_token"])
    assert client.get("/api/admin/users", headers=_bearer(user_token)).status_code == 403
    assert (
        client.post("/api/admin/users", json=_payload(username="bob"), headers=_bearer(user_token))
    ).status_code == 403
