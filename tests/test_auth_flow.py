"""End-to-end auth flow over the real app (TestClient + in-memory SQLite).

Covers bootstrap admin, the forced first change (no current password) vs the
normal change (current password required), the must-change-password gate on
functional endpoints, refresh rotation and reuse detection, logout."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _login(client: TestClient, password: str) -> str:
    resp = client.post("/api/auth/login", json={"username": "admin", "password": password})
    assert resp.status_code == 200, resp.text
    return str(resp.json()["access_token"])


def test_health_reports_version_and_db(client: TestClient) -> None:
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"
    assert body["version"] == "9.9.9-test"


def test_full_auth_flow(client: TestClient) -> None:
    # Wrong credentials → generic 401 (account state never leaks, AUTH-R10).
    bad = client.post("/api/auth/login", json={"username": "admin", "password": "nope"})
    assert bad.status_code == 401
    assert bad.json()["code"] == "invalid_credentials"

    access = _login(client, "initpass123")

    # /api/me is reachable during the forced-change state and reports it (it drives
    # the SPA boot, so it is exempt from the gate).
    me = client.get("/api/me", headers=_auth(access))
    assert me.status_code == 200
    profile = me.json()
    assert profile["username"] == "admin"
    assert profile["first_name"] == "Admin"
    assert profile["must_change_password"] is True

    # A gated functional endpoint (PATCH /me) is blocked during the forced change.
    gated = client.patch("/api/me", headers=_auth(access), json={"locale": "en"})
    assert gated.status_code == 403
    assert gated.json()["code"] == "must_change_password"

    # The forced first change does NOT require the current password.
    changed = client.post(
        "/api/auth/change-password", headers=_auth(access), json={"new_password": "newpass123"}
    )
    assert changed.status_code == 204

    # Password change is a global logout (AUTH-R5): re-login with the new password.
    access2 = _login(client, "newpass123")
    me2 = client.get("/api/me", headers=_auth(access2))
    assert me2.status_code == 200
    assert me2.json()["must_change_password"] is False

    # The gate is lifted now: PATCH /me works.
    assert client.patch("/api/me", headers=_auth(access2), json={"locale": "en"}).status_code == 200

    # Refresh rotates; reusing the stale refresh is theft → 401 + global logout.
    refresh2 = client.post("/api/auth/login", json={"username": "admin", "password": "newpass123"})
    refresh_token = refresh2.json()["refresh_token"]
    assert (
        client.post("/api/auth/refresh", json={"refresh_token": refresh_token}).status_code == 200
    )
    reuse = client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
    assert reuse.status_code == 401
    assert reuse.json()["code"] == "refresh_reuse"


def test_normal_change_requires_and_verifies_current_password(client: TestClient) -> None:
    # Clear the forced flag first (forced change needs no current password).
    access = _login(client, "initpass123")
    assert (
        client.post(
            "/api/auth/change-password", headers=_auth(access), json={"new_password": "newpass123"}
        ).status_code
        == 204
    )
    access2 = _login(client, "newpass123")

    # Missing current password → 400 (a normal change requires it).
    missing = client.post(
        "/api/auth/change-password", headers=_auth(access2), json={"new_password": "another123"}
    )
    assert missing.status_code == 400
    assert missing.json()["code"] == "old_password_required"

    # Wrong current password → 400.
    wrong = client.post(
        "/api/auth/change-password",
        headers=_auth(access2),
        json={"old_password": "WRONG", "new_password": "another123"},
    )
    assert wrong.status_code == 400
    assert wrong.json()["code"] == "invalid_old_password"

    # Correct current password → 204.
    ok = client.post(
        "/api/auth/change-password",
        headers=_auth(access2),
        json={"old_password": "newpass123", "new_password": "another123"},
    )
    assert ok.status_code == 204


def test_logout_then_refresh_is_rejected(client: TestClient) -> None:
    login = client.post("/api/auth/login", json={"username": "admin", "password": "initpass123"})
    access = login.json()["access_token"]
    refresh = login.json()["refresh_token"]

    assert client.post("/api/auth/logout", headers=_auth(access)).status_code == 204

    after = client.post("/api/auth/refresh", json={"refresh_token": refresh})
    assert after.status_code == 401
