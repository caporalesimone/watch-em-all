"""End-to-end auth flow over the real app (TestClient + in-memory SQLite).

Covers bootstrap admin, the forced first change (no current password) vs the
normal change (current password required), the must-change-password gate on
functional endpoints, refresh rotation and reuse detection, logout."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from src.core.db import new_session
from src.core.models import User


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
    assert "server_time" in body  # ISO8601 server clock (4.F1)


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


def test_password_changed_at_follows_the_password(client: TestClient) -> None:
    """10.X1: the column exists, is stamped at creation, and moves on every change.

    It is written an MVP before `password_expiry` (10.B19) reads it, so the only thing
    provable today is that the value tracks the password rather than staying at the
    bootstrap instant — which is the whole point of measuring an age against it.
    """
    session = new_session()
    try:
        at_creation = session.scalars(select(User).where(User.username == "admin")).one()
        stamped = at_creation.password_changed_at
    finally:
        session.close()
    assert stamped is not None, "the bootstrap admin must carry a creation stamp, never NULL"

    access = _login(client, "initpass123")
    assert (
        client.post(
            "/api/auth/change-password", headers=_auth(access), json={"new_password": "newpass123"}
        ).status_code
        == 204
    )

    session = new_session()
    try:
        after = session.scalars(select(User).where(User.username == "admin")).one()
        assert after.password_changed_at > stamped
    finally:
        session.close()


def test_logout_then_refresh_is_rejected(client: TestClient) -> None:
    login = client.post("/api/auth/login", json={"username": "admin", "password": "initpass123"})
    access = login.json()["access_token"]
    refresh = login.json()["refresh_token"]

    assert client.post("/api/auth/logout", headers=_auth(access)).status_code == 204

    after = client.post("/api/auth/refresh", json={"refresh_token": refresh})
    assert after.status_code == 401


def test_an_old_password_is_forced_to_change_at_the_next_sign_in(client: TestClient) -> None:
    """10.B19: expiry reuses the forced-change flow rather than refusing the login.

    The account is not in trouble — the password is old. Locking somebody out over age
    would be a punishment; sending them to the change page is the actual intent.
    """
    access = _login(client, "initpass123")
    assert (
        client.post(
            "/api/auth/change-password", headers=_auth(access), json={"new_password": "newpass123"}
        ).status_code
        == 204
    )
    token = _login(client, "newpass123")
    assert client.get("/api/me", headers=_auth(token)).json()["must_change_password"] is False

    # Off by default: turning it on is what makes anything happen.
    client.patch("/api/admin/settings", headers=_auth(token), json={"password_expiry_days": 30})
    session = new_session()
    try:
        user = session.scalars(select(User).where(User.username == "admin")).one()
        user.password_changed_at = datetime.now(UTC) - timedelta(days=31)
        session.commit()
    finally:
        session.close()

    aged = _login(client, "newpass123")  # still gets in
    assert client.get("/api/me", headers=_auth(aged)).json()["must_change_password"] is True


def test_expiry_off_leaves_an_ancient_password_alone(client: TestClient) -> None:
    access = _login(client, "initpass123")
    client.post(
        "/api/auth/change-password", headers=_auth(access), json={"new_password": "newpass123"}
    )
    session = new_session()
    try:
        user = session.scalars(select(User).where(User.username == "admin")).one()
        user.password_changed_at = datetime.now(UTC) - timedelta(days=4000)
        session.commit()
    finally:
        session.close()
    token = _login(client, "newpass123")
    assert client.get("/api/me", headers=_auth(token)).json()["must_change_password"] is False
