"""Tests for admin user management: create, list, reset, enable/disable (user-management.md)."""

from __future__ import annotations

from datetime import datetime, timedelta

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
        "username": "alice@example.com",
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
    assert created["username"] == "alice@example.com"
    assert created["role"] == "user"
    assert created["must_change_password"] is True
    assert created["last_login_at"] is None

    listed = client.get("/api/admin/users", headers=_bearer(token)).json()
    assert {u["username"] for u in listed} == {"admin", "alice@example.com"}


def test_created_user_can_log_in(client: TestClient) -> None:
    token = _admin_token(client)
    client.post("/api/admin/users", json=_payload(), headers=_bearer(token))
    # The new user logs in with the temporary password and is forced to change it.
    login = client.post(
        "/api/auth/login", json={"username": "alice@example.com", "password": "temp-pass-123"}
    )
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


# --------------------------------------------------------------- the username is an address


def test_a_username_that_is_not_an_address_is_refused(client: TestClient) -> None:
    """10.B23. The page validates too, but the page can be skipped with one ``curl`` — so the
    refusal has to come from here, which is why the test talks to the API and not to a form."""
    token = _admin_token(client)
    for bad in ("pippo", "pippo@", "@example.com", "two@@example.com", "no.dots@localhost"):
        resp = client.post("/api/admin/users", json=_payload(username=bad), headers=_bearer(token))
        assert resp.status_code == 400, f"{bad!r} was accepted as a username"


def test_a_username_is_stored_lowercase_and_matched_case_insensitively(
    client: TestClient,
) -> None:
    """Typed with capitals, stored without: an address is case-insensitive in practice, and the
    normalisation happens on write so the login can stay a plain indexed equality (10.B23)."""
    token = _admin_token(client)
    created = client.post(
        "/api/admin/users",
        json=_payload(username="Mario.Rossi@X.IT"),
        headers=_bearer(token),
    )
    assert created.status_code == 201
    assert created.json()["username"] == "mario.rossi@x.it"

    # And the same account answers to any casing at the login form.
    for typed in ("mario.rossi@x.it", "Mario.Rossi@X.IT", "  MARIO.ROSSI@x.it  "):
        login = client.post(
            "/api/auth/login", json={"username": typed, "password": "temp-pass-123"}
        )
        assert login.status_code == 200, f"{typed!r} did not reach the account"


def test_a_second_account_cannot_take_the_same_address_in_another_case(
    client: TestClient,
) -> None:
    token = _admin_token(client)
    client.post(
        "/api/admin/users", json=_payload(username="dup@example.com"), headers=_bearer(token)
    )
    dup = client.post(
        "/api/admin/users", json=_payload(username="DUP@Example.COM"), headers=_bearer(token)
    )
    assert dup.status_code == 409, "casing is not a way to own the same address twice"


def _all(client: TestClient, token: str) -> list[dict[str, object]]:
    listed: list[dict[str, object]] = client.get("/api/admin/users", headers=_bearer(token)).json()
    return listed


def _names(client: TestClient, token: str, status_filter: str) -> set[str]:
    listed = client.get(f"/api/admin/users?status={status_filter}", headers=_bearer(token)).json()
    return {str(u["username"]) for u in listed}


def _alice_id(client: TestClient, token: str) -> int:
    client.post("/api/admin/users", json=_payload(), headers=_bearer(token))
    listed = client.get("/api/admin/users", headers=_bearer(token)).json()
    return int(next(u["id"] for u in listed if u["username"] == "alice@example.com"))


def test_list_sorts_by_last_login_with_the_never_seen_at_the_dormant_end(
    client: TestClient,
) -> None:
    """10.B2: the sort exists to find dormant accounts, so 'never signed in' is the extreme."""
    token = _admin_token(client)
    client.post("/api/admin/users", json=_payload(), headers=_bearer(token))
    client.post(
        "/api/admin/users", json=_payload(username="bob@example.com"), headers=_bearer(token)
    )
    # Only alice ever signs in; bob never does. The admin has just logged in too.
    client.post(
        "/api/auth/login", json={"username": "alice@example.com", "password": "temp-pass-123"}
    )

    oldest_first = client.get(
        "/api/admin/users?sort=last_login&order=asc", headers=_bearer(token)
    ).json()
    assert oldest_first[0]["username"] == "bob@example.com", (
        "never signed in is the most dormant of all"
    )
    assert oldest_first[0]["last_login_at"] is None

    newest_first = client.get(
        "/api/admin/users?sort=last_login&order=desc", headers=_bearer(token)
    ).json()
    assert newest_first[-1]["username"] == "bob@example.com", (
        "and it belongs at the other end reversed"
    )


def test_list_filters_by_status_without_overlap(client: TestClient) -> None:
    token = _admin_token(client)
    uid = _alice_id(client, token)
    client.post(
        "/api/admin/users", json=_payload(username="bob@example.com"), headers=_bearer(token)
    )
    client.patch(f"/api/admin/users/{uid}", json={"is_active": False}, headers=_bearer(token))

    assert _names(client, token, "active") == {"admin", "bob@example.com"}
    assert _names(client, token, "disabled") == {"alice@example.com"}
    assert _names(client, token, "deleting") == set()  # nothing is marked yet — that is 10.B3
    assert len(_all(client, token)) == 3


def test_reset_password_forces_a_change_and_kills_the_old_sessions(client: TestClient) -> None:
    token = _admin_token(client)
    uid = _alice_id(client, token)
    # Alice is settled in: temporary password changed, a live session in hand.
    first = client.post(
        "/api/auth/login", json={"username": "alice@example.com", "password": "temp-pass-123"}
    )
    access = first.json()["access_token"]
    client.post(
        "/api/auth/change-password",
        json={"new_password": "alice-pass-123"},
        headers=_bearer(access),
    )
    live = client.post(
        "/api/auth/login", json={"username": "alice@example.com", "password": "alice-pass-123"}
    )
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
        client.post(
            "/api/auth/login", json={"username": "alice@example.com", "password": "alice-pass-123"}
        )
    ).status_code == 401
    again = client.post(
        "/api/auth/login", json={"username": "alice@example.com", "password": "reset-pass-123"}
    )
    assert again.status_code == 200


def test_disabling_locks_the_account_out_within_the_token_life(client: TestClient) -> None:
    token = _admin_token(client)
    uid = _alice_id(client, token)
    live = client.post(
        "/api/auth/login", json={"username": "alice@example.com", "password": "temp-pass-123"}
    )
    live_refresh = str(live.json()["refresh_token"])

    off = client.patch(f"/api/admin/users/{uid}", json={"is_active": False}, headers=_bearer(token))
    assert off.status_code == 200 and off.json()["is_active"] is False
    # Out within the life of the access token, which is what the phase promises: the session
    # cannot be renewed, and a new one cannot be opened.
    assert (
        client.post("/api/auth/refresh", json={"refresh_token": live_refresh})
    ).status_code == 401
    # Right password, disabled account → its own code, not "invalid credentials" (AUTH-R10).
    denied = client.post(
        "/api/auth/login", json={"username": "alice@example.com", "password": "temp-pass-123"}
    )
    assert denied.status_code == 403
    assert denied.json()["code"] == "account_disabled"

    on = client.patch(f"/api/admin/users/{uid}", json={"is_active": True}, headers=_bearer(token))
    assert on.status_code == 200 and on.json()["is_active"] is True
    assert (
        client.post(
            "/api/auth/login", json={"username": "alice@example.com", "password": "temp-pass-123"}
        )
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
        json=_payload(username="second-admin@example.com", role="admin"),
        headers=_bearer(token),
    )
    listed = client.get("/api/admin/users", headers=_bearer(token)).json()
    other = next(u["id"] for u in listed if u["username"] == "second-admin@example.com")
    allowed = client.patch(
        f"/api/admin/users/{other}", json={"is_active": False}, headers=_bearer(token)
    )
    assert allowed.status_code == 200, "an admin may disable a different admin"


def test_soft_delete_sets_a_deadline_and_destroys_nothing(client: TestClient) -> None:
    token = _admin_token(client)
    uid = _alice_id(client, token)

    marked = client.delete(f"/api/admin/users/{uid}", headers=_bearer(token)).json()
    assert marked["deletion_marked_at"] is not None
    assert marked["deletion_due_at"] is not None
    assert marked["is_active"] is False
    # The row is still there — that is the whole point of a soft delete.
    assert "alice@example.com" in {u["username"] for u in _all(client, token)}
    assert _names(client, token, "deleting") == {"alice@example.com"}
    # And she is out: right password, but the account is on its way to being destroyed.
    denied = client.post(
        "/api/auth/login", json={"username": "alice@example.com", "password": "temp-pass-123"}
    )
    assert denied.status_code == 403
    assert denied.json()["code"] == "account_disabled"


def test_restore_brings_the_account_back_disabled_never_active(client: TestClient) -> None:
    token = _admin_token(client)
    uid = _alice_id(client, token)
    client.delete(f"/api/admin/users/{uid}", headers=_bearer(token))

    back = client.post(f"/api/admin/users/{uid}/restore", headers=_bearer(token)).json()
    assert back["deletion_marked_at"] is None and back["deletion_due_at"] is None
    # Undoing a deletion says "do not destroy this", which is less than "let them back in".
    assert back["is_active"] is False
    assert _names(client, token, "disabled") == {"alice@example.com"}
    assert (
        client.post(
            "/api/auth/login", json={"username": "alice@example.com", "password": "temp-pass-123"}
        )
    ).status_code == 403

    client.patch(f"/api/admin/users/{uid}", json={"is_active": True}, headers=_bearer(token))
    assert (
        client.post(
            "/api/auth/login", json={"username": "alice@example.com", "password": "temp-pass-123"}
        )
    ).status_code == 200


def test_restoring_an_account_that_is_not_going_anywhere_is_a_409(client: TestClient) -> None:
    token = _admin_token(client)
    uid = _alice_id(client, token)
    refused = client.post(f"/api/admin/users/{uid}/restore", headers=_bearer(token))
    assert refused.status_code == 409
    assert refused.json()["code"] == "not_being_deleted"


def test_changing_the_grace_period_does_not_move_a_deadline_already_set(
    client: TestClient,
) -> None:
    """10.B7: the due date is a fact about that marking, not a formula re-read later."""
    token = _admin_token(client)
    uid = _alice_id(client, token)
    marked = client.delete(f"/api/admin/users/{uid}", headers=_bearer(token)).json()
    original_deadline = marked["deletion_due_at"]

    changed = client.patch(
        "/api/admin/settings", json={"user_deletion_retention_days": 1}, headers=_bearer(token)
    )
    assert changed.status_code == 200
    assert changed.json()["user_deletion_retention_days"] == 1

    still = next(u for u in _all(client, token) if u["username"] == "alice@example.com")
    assert still["deletion_due_at"] == original_deadline, (
        "shortening the grace period must not pull an account's execution date forward"
    )

    # New markings do get the new period — that is the difference between the two.
    client.post(
        "/api/admin/users", json=_payload(username="bob@example.com"), headers=_bearer(token)
    )
    bob = next(u for u in _all(client, token) if u["username"] == "bob@example.com")
    fresh = client.delete(f"/api/admin/users/{bob['id']}", headers=_bearer(token)).json()
    marked_at = datetime.fromisoformat(fresh["deletion_marked_at"])
    due_at = datetime.fromisoformat(fresh["deletion_due_at"])
    assert due_at - marked_at == timedelta(days=1)


def test_an_admin_cannot_delete_themselves(client: TestClient) -> None:
    token = _admin_token(client)
    me = client.get("/api/me", headers=_bearer(token)).json()
    refused = client.delete(f"/api/admin/users/{me['id']}", headers=_bearer(token))
    assert refused.status_code == 403
    assert refused.json()["code"] == "cannot_target_self"
    assert client.get("/api/me", headers=_bearer(token)).status_code == 200


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
    user_token = str(relogin.json()["access_token"])
    assert client.get("/api/admin/users", headers=_bearer(user_token)).status_code == 403
    assert (
        client.post(
            "/api/admin/users",
            json=_payload(username="bob@example.com"),
            headers=_bearer(user_token),
        )
    ).status_code == 403
