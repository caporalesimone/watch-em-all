"""Tests for the admin-only error feed (4.B0+, GET /api/admin/errors).

Admin-facing errors/warnings are admin-only by contract: never on the public
/api/health probe, never to a normal user or an anonymous caller.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _admin_token(client: TestClient) -> str:
    # Bootstrap admin starts with a forced change; clear it, then log in again so the
    # token is past the must-change gate require_admin enforces.
    login = client.post("/api/auth/login", json={"username": "admin", "password": "initpass123"})
    access = login.json()["access_token"]
    client.post(
        "/api/auth/change-password",
        json={"new_password": "adminpass123"},
        headers=_bearer(access),
    )
    relogin = client.post("/api/auth/login", json={"username": "admin", "password": "adminpass123"})
    return str(relogin.json()["access_token"])


def _user_token(client: TestClient, admin: str) -> str:
    client.post(
        "/api/admin/users",
        json={
            "username": "alice",
            "first_name": "Alice",
            "last_name": "Doe",
            "role": "user",
            "temp_password": "temp-pass-123",
        },
        headers=_bearer(admin),
    )
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
    return str(relogin.json()["access_token"])


def test_admin_errors_is_admin_only(client: TestClient) -> None:
    # Anonymous → 401; a normal user → 403. Never exposed off /api/admin.
    assert client.get("/api/admin/errors").status_code == 401
    admin = _admin_token(client)
    user = _user_token(client, admin)
    assert client.get("/api/admin/errors", headers=_bearer(user)).status_code == 403


def test_admin_errors_clean_is_empty(client: TestClient) -> None:
    admin = _admin_token(client)
    resp = client.get("/api/admin/errors", headers=_bearer(admin))
    assert resp.status_code == 200
    # Fresh test DB matches the models, and the conftest leaves the flag off → empty list.
    assert resp.json() == []
