"""Tests for admin user management: create, list, reset, enable/disable (user-management.md)."""

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


def _alice_id(client: TestClient, token: str) -> int:
    client.post("/api/admin/users", json=_payload(), headers=_bearer(token))
    listed = client.get("/api/admin/users", headers=_bearer(token)).json()
    return int(next(u["id"] for u in listed if u["username"] == "alice"))


def test_reset_password_forces_a_change_and_kills_the_old_sessions(client: TestClient) -> None:
    token = _admin_token(client)
    uid = _alice_id(client, token)
    # Alice is settled in: temporary password changed, a live session in hand.
    first = client.post("/api/auth/login", json={"username": "alice", "password": "temp-pass-123"})
    access = first.json()["access_token"]
    client.post(
        "/api/auth/change-password",
        json={"new_password": "alice-pass-123"},
        headers=_bearer(access),
    )
    live = client.post("/api/auth/login", json={"username": "alice", "password": "alice-pass-123"})
    live_refresh = str(live.json()["refresh_token"])

    reset = client.post(
        f"/api/admin/users/{uid}/reset-password",
        json={"temp_password": "reset-pass-123"},
        headers=_bearer(token),
    )
    assert reset.status_code == 200
    assert reset.json()["must_change_password"] is True
    # A reset exists for the case where somebody else may hold the old password, so the old
    # password stops working and the session cannot be renewed. The access token already
    # issued survives until it expires — that is the documented trade of not checking
    # `token_version` on every request, not an oversight.
    assert (
        client.post("/api/auth/refresh", json={"refresh_token": live_refresh})
    ).status_code == 401
    assert (
        client.post("/api/auth/login", json={"username": "alice", "password": "alice-pass-123"})
    ).status_code == 401
    again = client.post("/api/auth/login", json={"username": "alice", "password": "reset-pass-123"})
    assert again.status_code == 200


def test_disabling_locks_the_account_out_within_the_token_life(client: TestClient) -> None:
    token = _admin_token(client)
    uid = _alice_id(client, token)
    live = client.post("/api/auth/login", json={"username": "alice", "password": "temp-pass-123"})
    live_refresh = str(live.json()["refresh_token"])

    off = client.patch(f"/api/admin/users/{uid}", json={"is_active": False}, headers=_bearer(token))
    assert off.status_code == 200 and off.json()["is_active"] is False
    # Out within the life of the access token, which is what the phase promises: the session
    # cannot be renewed, and a new one cannot be opened.
    assert (
        client.post("/api/auth/refresh", json={"refresh_token": live_refresh})
    ).status_code == 401
    # Right password, disabled account → its own code, not "invalid credentials" (AUTH-R10).
    denied = client.post("/api/auth/login", json={"username": "alice", "password": "temp-pass-123"})
    assert denied.status_code == 403
    assert denied.json()["code"] == "account_disabled"

    on = client.patch(f"/api/admin/users/{uid}", json={"is_active": True}, headers=_bearer(token))
    assert on.status_code == 200 and on.json()["is_active"] is True
    assert (
        client.post("/api/auth/login", json={"username": "alice", "password": "temp-pass-123"})
    ).status_code == 200


def test_an_admin_cannot_disable_themselves_but_can_disable_another_admin(
    client: TestClient,
) -> None:
    """The guard is about who is asking, not about the target's role (10.B1)."""
    token = _admin_token(client)
    me = client.get("/api/me", headers=_bearer(token)).json()

    refused = client.patch(
        f"/api/admin/users/{me['id']}", json={"is_active": False}, headers=_bearer(token)
    )
    assert refused.status_code == 403
    assert refused.json()["code"] == "cannot_target_self"
    # Still signed in: the refusal has to leave the account exactly as it was.
    assert client.get("/api/me", headers=_bearer(token)).status_code == 200

    client.post(
        "/api/admin/users",
        json=_payload(username="second-admin", role="admin"),
        headers=_bearer(token),
    )
    listed = client.get("/api/admin/users", headers=_bearer(token)).json()
    other = next(u["id"] for u in listed if u["username"] == "second-admin")
    allowed = client.patch(
        f"/api/admin/users/{other}", json={"is_active": False}, headers=_bearer(token)
    )
    assert allowed.status_code == 200, "an admin may disable a different admin"


def test_unknown_account_is_a_404(client: TestClient) -> None:
    token = _admin_token(client)
    assert (
        client.patch("/api/admin/users/9999", json={"is_active": False}, headers=_bearer(token))
    ).status_code == 404
    assert (
        client.post(
            "/api/admin/users/9999/reset-password",
            json={"temp_password": "whatever-123"},
            headers=_bearer(token),
        )
    ).status_code == 404


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
