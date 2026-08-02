"""Tests for the dev feature flags (4.B1a): admin endpoints + the service."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.core.db import new_session
from src.core.feature_flags import clear_flags, set_flags, worker_tick_seconds


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


def _user_token(client: TestClient, admin: str) -> str:
    client.post(
        "/api/admin/users",
        json={
            "username": "alice@example.com",
            "first_name": "Alice",
            "last_name": "Doe",
            "role": "user",
            "temp_password": "temp-pass-123",
        },
        headers=_bearer(admin),
    )
    login = client.post(
        "/api/auth/login", json={"username": "alice@example.com", "password": "temp-pass-123"}
    )
    access = login.json()["access_token"]
    client.post(
        "/api/auth/change-password",
        json={"new_password": "alice-pass-123"},
        headers=_bearer(access),
    )
    relogin = client.post(
        "/api/auth/login", json={"username": "alice@example.com", "password": "alice-pass-123"}
    )
    return str(relogin.json()["access_token"])


def test_feature_flags_endpoint_is_admin_only(client: TestClient) -> None:
    assert client.get("/api/admin/feature-flags").status_code == 401
    admin = _admin_token(client)
    user = _user_token(client, admin)
    assert client.get("/api/admin/feature-flags", headers=_bearer(user)).status_code == 403


def test_feature_flags_get_default_then_patch_override(client: TestClient) -> None:
    h = _bearer(_admin_token(client))
    assert client.get("/api/admin/feature-flags", headers=h).json()["worker_tick"]["seconds"] == 60
    patched = client.patch(
        "/api/admin/feature-flags", json={"worker_tick": {"seconds": 5}}, headers=h
    )
    assert patched.status_code == 200
    assert patched.json()["worker_tick"]["seconds"] == 5
    assert client.get("/api/admin/feature-flags", headers=h).json()["worker_tick"]["seconds"] == 5


def test_feature_flags_unknown_key_rejected(client: TestClient) -> None:
    resp = client.patch(
        "/api/admin/feature-flags", json={"nope": {"x": 1}}, headers=_bearer(_admin_token(client))
    )
    assert resp.status_code == 422


def test_worker_tick_seconds_override_then_clear(client: TestClient) -> None:
    # Service level: default → override → clear → default (what the worker reads each tick).
    session = new_session()
    try:
        assert worker_tick_seconds(session) == 60
        set_flags(session, {"worker_tick": {"seconds": 7}})
        assert worker_tick_seconds(session) == 7
        clear_flags(session)
        assert worker_tick_seconds(session) == 60
    finally:
        session.close()
