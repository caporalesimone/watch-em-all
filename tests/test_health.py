"""Health endpoint, focused on the 4.B0 schema-drift exposure behind the flag."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def test_health_hides_schema_drift_when_flag_unset(client: TestClient) -> None:
    # The conftest fixture does not set WEA_SCHEMA_DRIFT_ALERT → defaults to off.
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["schema_drift"] is None


def test_health_exposes_schema_drift_when_flag_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        'core:\n  database_url: "sqlite+pysqlite:///:memory:"\n'
        '  secret_key: "${WEA_SECRET_KEY}"\n  default_locale: "en"\n'
        "  access_token_ttl_min: 15\n  refresh_token_ttl_days: 7\n",
        encoding="utf-8",
    )
    ver = tmp_path / "VERSION"
    ver.write_text("9.9.9-test\n", encoding="utf-8")
    monkeypatch.setenv("WEA_SECRET_KEY", "x" * 64)
    monkeypatch.setenv("WEA_ADMIN_INITIAL_USERNAME", "admin")
    monkeypatch.setenv("WEA_ADMIN_INITIAL_PASSWORD", "initpass123")
    monkeypatch.setenv("WEA_SCHEMA_DRIFT_ALERT", "true")

    from src.core import config as config_mod

    monkeypatch.setattr(config_mod, "CONFIG_PATH", str(cfg))
    monkeypatch.setattr(config_mod, "VERSION_PATH", str(ver))
    config_mod.get_settings.cache_clear()

    from src.web.app import create_app

    app = create_app()
    with TestClient(app) as test_client:
        body = test_client.get("/api/health").json()
    config_mod.get_settings.cache_clear()

    # Flag on + a fresh schema matching the models → drift is exposed, and empty.
    assert body["schema_drift"] == []
