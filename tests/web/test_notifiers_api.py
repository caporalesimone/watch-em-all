"""Notifier API tests (7.B3/7.B4): two-level config, secrets, state, kill-switch, in-app rules.

Uses the real loaded plugins (in_app + email). The email SMTP is monkeypatched where a test send is
exercised so no real connection is made.
"""

from __future__ import annotations

import smtplib
from typing import Any

import pytest
from fastapi.testclient import TestClient


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _admin_token(client: TestClient) -> str:
    login = client.post("/api/auth/login", json={"username": "admin", "password": "initpass123"})
    access = login.json()["access_token"]
    client.post(
        "/api/auth/change-password", json={"new_password": "adminpass123"}, headers=_bearer(access)
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
        },
        headers=_bearer(admin_token),
    )
    login = client.post("/api/auth/login", json={"username": username, "password": "temp-pass-123"})
    access = login.json()["access_token"]
    client.post(
        "/api/auth/change-password", json={"new_password": "userpass123"}, headers=_bearer(access)
    )
    relogin = client.post("/api/auth/login", json={"username": username, "password": "userpass123"})
    return str(relogin.json()["access_token"])


def _by_id(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {c["plugin_id"]: c for c in items}


def _save_email_config(client: TestClient, admin: str, **over: str) -> dict[str, Any]:
    config = {"smtp_host": "smtp.local", "from_address": "w@local", "smtp_password": "s3cret"}
    config.update(over)
    resp = client.put(
        "/api/admin/notifiers/email/config", json={"config": config}, headers=_bearer(admin)
    )
    return dict(resp.json())


def _configure_email_admin(client: TestClient, admin: str) -> None:
    """The whole admin-side flow, as a channel really becomes usable since 10.B28: save the
    settings, prove them, switch it on.

    The proof is stamped straight into the database rather than driven through the endpoint,
    because these tests are about what an *available* channel does — patching an SMTP server into
    every one of them would be paying for a send none of them is asking a question about. The
    validation endpoint has its own tests below, with a real (fake) server.
    """
    from src.core import notifiers as notif
    from src.core.db import new_session

    _save_email_config(client, admin)
    with new_session() as db:
        notif.mark_validated(db, "email")
    client.patch("/api/admin/notifiers/email", json={"enabled": True}, headers=_bearer(admin))


def test_user_lists_in_app_and_email(client: TestClient) -> None:
    token = _make_user(client, _admin_token(client), "alice@example.com")
    items = client.get("/api/notifiers", headers=_bearer(token)).json()
    channels = _by_id(items)
    assert items[0]["plugin_id"] == "in_app"  # in-app first
    assert channels["in_app"]["is_in_app"] and channels["in_app"]["active"]
    assert channels["email"]["available"] is False  # no admin config yet


def test_admin_config_makes_email_available_secret_write_only(client: TestClient) -> None:
    admin = _admin_token(client)
    _configure_email_admin(client, admin)
    admin_list = _by_id(client.get("/api/admin/notifiers", headers=_bearer(admin)).json())
    email = admin_list["email"]
    assert email["admin_config_complete"] is True
    assert email["is_set"]["smtp_password"] is True  # a value is stored…
    assert "smtp_password" not in email["config"]  # …but never returned (CFG-R3)

    token = _make_user(client, admin, "alice@example.com")
    assert _by_id(client.get("/api/notifiers", headers=_bearer(token)).json())["email"]["available"]


def test_email_has_no_user_config_left_and_arrives_switched_on(client: TestClient) -> None:
    """10.B25: the channel used to ask each person for a delivery address. Now the account is
    the address, so there is nothing to fill in — and a new account arrives with it on."""
    admin = _admin_token(client)
    _configure_email_admin(client, admin)
    token = _make_user(client, admin, "alice@example.com")

    email = _by_id(client.get("/api/notifiers", headers=_bearer(token)).json())["email"]
    assert email["user_schema"] == [], "the address is not a field any more"
    assert email["enabled"] is True, "a new account is reachable at its own address by default"
    assert email["active"] is True

    # And nothing a user posts can put a destination back: the key is not in the schema (CFG-R5).
    saved = client.put(
        "/api/notifiers/email/config",
        json={"config": {"to_address": "elsewhere@b.co", "smtp_host": "evil"}},
        headers=_bearer(token),
    ).json()
    assert saved["config"] == {}

    off = client.patch(
        "/api/notifiers/email", json={"enabled": False}, headers=_bearer(token)
    ).json()
    assert off["active"] is False


def test_in_app_cannot_be_user_configured_or_disabled(client: TestClient) -> None:
    token = _make_user(client, _admin_token(client), "alice@example.com")
    assert (
        client.put(
            "/api/notifiers/in_app/config", json={"config": {}}, headers=_bearer(token)
        ).json()["code"]
        == "in_app_no_config"
    )
    assert (
        client.patch(
            "/api/notifiers/in_app", json={"enabled": False}, headers=_bearer(token)
        ).json()["code"]
        == "in_app_always_active"
    )


def test_admin_kill_switch_hides_email_from_users(client: TestClient) -> None:
    admin = _admin_token(client)
    _configure_email_admin(client, admin)
    client.patch("/api/admin/notifiers/email", json={"enabled": False}, headers=_bearer(admin))
    token = _make_user(client, admin, "alice@example.com")
    assert "email" not in _by_id(client.get("/api/notifiers", headers=_bearer(token)).json())


def test_admin_disabling_in_app_hides_inbox(client: TestClient) -> None:
    admin = _admin_token(client)
    token = _make_user(client, admin, "alice@example.com")
    # Baseline: in-app listed, alerts endpoint reachable.
    assert "in_app" in _by_id(client.get("/api/notifiers", headers=_bearer(token)).json())
    client.patch("/api/admin/notifiers/in_app", json={"enabled": False}, headers=_bearer(admin))
    assert "in_app" not in _by_id(client.get("/api/notifiers", headers=_bearer(token)).json())
    page = client.get("/api/alerts", headers=_bearer(token)).json()
    assert page["items"] == [] and page["total"] == 0
    assert client.get("/api/alerts/unread-count", headers=_bearer(token)).json()["count"] == 0


def test_the_profile_has_no_test_send_anymore(client: TestClient) -> None:
    """10.X4: the user-facing probe is gone, not hidden. A route left in place and unlinked is
    a route that comes back the next time somebody reads the OpenAPI page."""
    admin = _admin_token(client)
    token = _make_user(client, admin, "alice@example.com")
    assert client.post("/api/notifiers/email/test", headers=_bearer(token)).status_code == 404


# --- validating a channel (10.B28) --------------------------------------------------------


def _fake_smtp(monkeypatch: pytest.MonkeyPatch, *, refuse: bool = False) -> list[Any]:
    """A stand-in SMTP server. Returns the list it delivers into."""
    sent: list[Any] = []

    class _FakeSMTP:
        def __init__(self, *a: object, **k: object) -> None:
            if refuse:
                raise OSError("connection refused")

        def __enter__(self) -> _FakeSMTP:
            return self

        def __exit__(self, *a: object) -> None: ...

        def starttls(self, context: object = None) -> None: ...
        def login(self, u: str, p: str) -> None: ...

        def send_message(self, msg: Any) -> None:
            sent.append(msg)

    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    return sent


def test_validating_sends_a_real_message_to_the_admins_own_account(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The destination is not typed anywhere — it is the account's own (10.B25), which is a
    better test of the system config than an address supplied for the occasion."""
    admin = _admin_token(client)
    _save_email_config(client, admin)
    # The bootstrap admin's username is not an address, so it carries a contact email (10.X2);
    # that is where its own mail goes.
    client.patch(
        "/api/me", json={"contact_email": "boss@example.com"}, headers=_bearer(admin)
    ).raise_for_status()

    sent = _fake_smtp(monkeypatch)
    res = client.post("/api/admin/notifiers/email/validate", headers=_bearer(admin)).json()

    assert res["ok"] is True
    assert sent and sent[0]["To"] == "boss@example.com"
    assert res["channel"]["validated"] is True
    assert res["channel"]["validated_at"] is not None


def test_a_channel_cannot_be_switched_on_before_it_is_validated(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin = _admin_token(client)
    saved = _save_email_config(client, admin)
    assert saved["enabled"] is False, "a channel that has to prove itself starts off"
    assert saved["validated"] is False

    refused = client.patch(
        "/api/admin/notifiers/email", json={"enabled": True}, headers=_bearer(admin)
    )
    assert refused.status_code == 422
    assert refused.json()["code"] == "not_validated"

    _fake_smtp(monkeypatch)
    client.post("/api/admin/notifiers/email/validate", headers=_bearer(admin))
    on = client.patch(
        "/api/admin/notifiers/email", json={"enabled": True}, headers=_bearer(admin)
    ).json()
    assert on["enabled"] is True


def test_a_server_that_refuses_the_message_validates_nothing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Otherwise a channel drifts into "validated" by having been tried."""
    admin = _admin_token(client)
    _save_email_config(client, admin)
    _fake_smtp(monkeypatch, refuse=True)

    res = client.post("/api/admin/notifiers/email/validate", headers=_bearer(admin)).json()
    assert res["ok"] is False and res["error"]
    assert res["channel"]["validated"] is False


def test_changing_a_setting_undoes_the_proof_and_switches_the_channel_off(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The invalidation is a fingerprint comparison, not a flag somebody has to remember to
    clear — which is why it cannot be forgotten on a path that writes the config."""
    admin = _admin_token(client)
    _save_email_config(client, admin)
    _fake_smtp(monkeypatch)
    client.post("/api/admin/notifiers/email/validate", headers=_bearer(admin))
    client.patch("/api/admin/notifiers/email", json={"enabled": True}, headers=_bearer(admin))

    moved = _save_email_config(client, admin, smtp_host="elsewhere.local")
    assert moved["validated"] is False, "the proof was about the old host"
    assert moved["enabled"] is False, "and a channel nothing has proven is not on"

    # Saving the same values again is not a change, so it costs nothing.
    _fake_smtp(monkeypatch)
    client.post("/api/admin/notifiers/email/validate", headers=_bearer(admin))
    client.patch("/api/admin/notifiers/email", json={"enabled": True}, headers=_bearer(admin))
    again = _save_email_config(client, admin, smtp_host="elsewhere.local")
    assert again["validated"] is True and again["enabled"] is True


def test_an_unvalidated_channel_never_reaches_a_user(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two gates, and both matter. Saving settings leaves the channel off, so it is not even
    listed; and the composite state checks the proof itself rather than trusting the flag,
    because a channel with **no** admin row counts as enabled by default — on a fresh
    installation the flag alone would let an unproven channel deliver."""
    from src.core.db import new_session
    from src.core.notifiers import set_admin_enabled

    admin = _admin_token(client)
    _save_email_config(client, admin)
    token = _make_user(client, admin, "alice@example.com")
    assert "email" not in _by_id(client.get("/api/notifiers", headers=_bearer(token)).json())

    # Force the flag on behind the API's back — the state still refuses, because what makes a
    # channel available is the proof, not the switch.
    with new_session() as db:
        set_admin_enabled(db, "email", True)
    listed = _by_id(client.get("/api/notifiers", headers=_bearer(token)).json())
    assert listed["email"]["available"] is False

    _fake_smtp(monkeypatch)
    client.post("/api/admin/notifiers/email/validate", headers=_bearer(admin))
    listed = _by_id(client.get("/api/notifiers", headers=_bearer(token)).json())
    assert listed["email"]["available"] is True


def test_validating_an_incomplete_config_is_refused(client: TestClient) -> None:
    admin = _admin_token(client)
    client.put(
        "/api/admin/notifiers/email/config",
        json={"config": {"smtp_host": "smtp.local"}},  # no from_address
        headers=_bearer(admin),
    )
    refused = client.post("/api/admin/notifiers/email/validate", headers=_bearer(admin))
    assert refused.status_code == 422
    assert refused.json()["code"] == "config_incomplete"
