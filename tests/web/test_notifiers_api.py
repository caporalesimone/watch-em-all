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
            "temp_password": "temp-pass-123",
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


def _configure_email_admin(client: TestClient, admin: str) -> None:
    client.put(
        "/api/admin/notifiers/email/config",
        json={
            "config": {
                "smtp_host": "smtp.local",
                "from_address": "w@local",
                "smtp_password": "s3cret",
            }
        },
        headers=_bearer(admin),
    )


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


def test_user_config_enable_makes_email_active_and_filters_admin_keys(client: TestClient) -> None:
    admin = _admin_token(client)
    _configure_email_admin(client, admin)
    token = _make_user(client, admin, "alice@example.com")

    # Inject an admin key alongside the user field: it must be dropped (CFG-R5).
    saved = client.put(
        "/api/notifiers/email/config",
        json={"config": {"to_address": "a@b.co", "smtp_host": "evil"}},
        headers=_bearer(token),
    ).json()
    assert saved["config"] == {"to_address": "a@b.co"}
    assert saved["user_config_complete"] and saved["active"] is False  # not enabled yet

    enabled = client.patch(
        "/api/notifiers/email", json={"enabled": True}, headers=_bearer(token)
    ).json()
    assert enabled["active"] is True


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


def test_user_test_endpoint_reports_outcome(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin = _admin_token(client)
    _configure_email_admin(client, admin)
    token = _make_user(client, admin, "alice@example.com")
    client.put(
        "/api/notifiers/email/config",
        json={"config": {"to_address": "a@b.co"}},
        headers=_bearer(token),
    )

    class _FakeSMTP:
        def __init__(self, *a: object, **k: object) -> None: ...
        def __enter__(self) -> _FakeSMTP:
            return self

        def __exit__(self, *a: object) -> None: ...

        def starttls(self, context: object = None) -> None: ...
        def login(self, u: str, p: str) -> None: ...
        def send_message(self, msg: object) -> None: ...

    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    res = client.post("/api/notifiers/email/test", headers=_bearer(token)).json()
    assert res["ok"] is True
