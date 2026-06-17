from __future__ import annotations

from pathlib import Path

import pytest

from src.core import config as config_mod
from src.core.config import ConfigError, load_settings


def _write(tmp_path: Path, body: str) -> Path:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(body, encoding="utf-8")
    return cfg


def test_interpolation_resolves_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PGUSER", "alice")
    monkeypatch.setenv("PGPASS", "s3cret")
    monkeypatch.setenv("SECRET_KEY", "k" * 32)
    monkeypatch.setattr(config_mod, "VERSION_PATH", str(tmp_path / "missing"))  # → fallback
    cfg = _write(
        tmp_path,
        "core:\n"
        '  database_url: "postgresql+psycopg://${PGUSER}:${PGPASS}@db:5432/wea"\n'
        '  secret_key: "${SECRET_KEY}"\n'
        "  access_token_ttl_min: 15\n"
        "  refresh_token_ttl_days: 7\n",
    )
    settings = load_settings(cfg)
    assert settings.core.database_url == "postgresql+psycopg://alice:s3cret@db:5432/wea"
    assert settings.core.secret_key == "k" * 32
    assert settings.version == "0.0.0-unknown"  # version file absent → clear fallback


def test_missing_required_env_raises_clear_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("NOPE", raising=False)
    cfg = _write(
        tmp_path,
        "core:\n"
        '  database_url: "${NOPE}"\n'
        '  secret_key: "0123456789abcdef0123"\n'
        "  access_token_ttl_min: 15\n"
        "  refresh_token_ttl_days: 7\n",
    )
    with pytest.raises(ConfigError, match="NOPE"):
        load_settings(cfg)


def test_default_syntax_when_unset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MAYBE", raising=False)
    version_file = tmp_path / "v"
    version_file.write_text("1.2.3", encoding="utf-8")
    monkeypatch.setattr(config_mod, "VERSION_PATH", str(version_file))
    cfg = _write(
        tmp_path,
        "core:\n"
        '  database_url: "${MAYBE:-sqlite+pysqlite:///:memory:}"\n'
        '  secret_key: "0123456789abcdef0123"\n'
        "  access_token_ttl_min: 15\n"
        "  refresh_token_ttl_days: 7\n",
    )
    settings = load_settings(cfg)
    assert settings.core.database_url == "sqlite+pysqlite:///:memory:"
    assert settings.version == "1.2.3"
