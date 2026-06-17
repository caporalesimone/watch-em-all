"""End-to-end auth flow over the real app (TestClient + in-memory SQLite).

Covers bootstrap admin, the forced password change gate, refresh rotation and
reuse detection, profile, logout — the heart of phase-1 auth (auth.md)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


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

    # Correct initial credentials → token pair; must_change_password is pending.
    login = client.post("/api/auth/login", json={"username": "admin", "password": "initpass123"})
    assert login.status_code == 200
    access = login.json()["access_token"]

    # AUTH-R7: a protected endpoint is gated until the password is changed.
    me_gated = client.get("/api/me", headers=_auth(access))
    assert me_gated.status_code == 403
    assert me_gated.json()["code"] == "must_change_password"

    # change-password works while gated (logout/change-password are exempt).
    changed = client.post(
        "/api/auth/change-password",
        headers=_auth(access),
        json={"old_password": "initpass123", "new_password": "newpass123"},
    )
    assert changed.status_code == 204

    # Password change is a global logout (AUTH-R5): the old session must re-login.
    relogin = client.post("/api/auth/login", json={"username": "admin", "password": "newpass123"})
    assert relogin.status_code == 200
    access2 = relogin.json()["access_token"]
    refresh2 = relogin.json()["refresh_token"]

    me = client.get("/api/me", headers=_auth(access2))
    assert me.status_code == 200
    profile = me.json()
    assert profile["username"] == "admin"
    assert profile["role"] == "admin"
    assert profile["must_change_password"] is False

    # Profile locale: only 'en' accepted in V1.
    assert client.patch("/api/me", headers=_auth(access2), json={"locale": "en"}).status_code == 200
    bad_locale = client.patch("/api/me", headers=_auth(access2), json={"locale": "it"})
    assert bad_locale.status_code == 400
    assert bad_locale.json()["code"] == "unsupported_locale"

    # Refresh rotates the pair.
    rotated = client.post("/api/auth/refresh", json={"refresh_token": refresh2})
    assert rotated.status_code == 200
    assert rotated.json()["refresh_token"] != refresh2

    # Reusing the now-stale refresh is treated as theft → 401 + global logout.
    reuse = client.post("/api/auth/refresh", json={"refresh_token": refresh2})
    assert reuse.status_code == 401
    assert reuse.json()["code"] == "refresh_reuse"


def test_logout_then_refresh_is_rejected(client: TestClient) -> None:
    login = client.post("/api/auth/login", json={"username": "admin", "password": "initpass123"})
    access = login.json()["access_token"]
    refresh = login.json()["refresh_token"]

    assert client.post("/api/auth/logout", headers=_auth(access)).status_code == 204

    # token_version bumped by logout → the old refresh no longer validates.
    after = client.post("/api/auth/refresh", json={"refresh_token": refresh})
    assert after.status_code == 401
