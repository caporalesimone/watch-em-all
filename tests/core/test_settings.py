"""Tests for system settings (4.B5 defaults + 4.F7 editor)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from src.core.db import Base
from src.core.settings import get_system_settings, set_system_settings


def _standalone() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return Session(engine)


def test_defaults_when_no_overrides() -> None:
    with _standalone() as session:
        settings = get_system_settings(session)
    assert settings.scraper_run_timeout_min == 30
    assert settings.log_retention_days == 90


def test_set_merges_validates_and_rejects() -> None:
    with _standalone() as session:
        set_system_settings(session, {"log_retention_days": 30})
        s = get_system_settings(session)
        assert s.log_retention_days == 30
        assert s.scraper_run_timeout_min == 30  # untouched key keeps its default
        with pytest.raises(ValueError):  # unknown key
            set_system_settings(session, {"nope": 1})
        with pytest.raises(ValidationError):  # below range
            set_system_settings(session, {"scraper_run_timeout_min": 0})
        with pytest.raises(ValidationError):  # below range
            set_system_settings(session, {"log_retention_days": -1})


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


def test_settings_endpoint_requires_admin(client: TestClient) -> None:
    assert client.get("/api/admin/settings").status_code == 401
    assert client.patch("/api/admin/settings", json={"log_retention_days": 7}).status_code == 401


def test_settings_get_defaults_then_patch(client: TestClient) -> None:
    h = _bearer(_admin_token(client))
    assert client.get("/api/admin/settings", headers=h).json() == {
        "scraper_run_timeout_min": 30,
        "catchup_warning_min": 10,
        "log_retention_days": 90,
        "user_deletion_retention_days": 30,
        # Off by default (10.B19): the feature is opt-in, and this assertion is the guard
        # that it stays that way — a default of anything else would put every account on a
        # forced password change without an admin ever asking for one.
        "password_expiry_days": 0,
        # The nightly window and what it leaves behind (10.B8a/b).
        "maintenance_hour": 7,
        "alert_keep_last": 100,
    }
    patched = client.patch(
        "/api/admin/settings",
        json={"log_retention_days": 7, "scraper_run_timeout_min": 60},
        headers=h,
    )
    assert patched.status_code == 200
    body = patched.json()
    assert body["log_retention_days"] == 7
    assert body["scraper_run_timeout_min"] == 60
    assert body["catchup_warning_min"] == 10  # untouched
    assert client.get("/api/admin/settings", headers=h).json()["log_retention_days"] == 7


def test_settings_rejects_unknown_and_out_of_range(client: TestClient) -> None:
    h = _bearer(_admin_token(client))
    assert client.patch("/api/admin/settings", json={"nope": 1}, headers=h).status_code == 422
    assert (
        client.patch("/api/admin/settings", json={"scraper_run_timeout_min": 0}, headers=h)
    ).status_code == 422
    assert (
        client.patch("/api/admin/settings", json={"log_retention_days": -1}, headers=h)
    ).status_code == 422
