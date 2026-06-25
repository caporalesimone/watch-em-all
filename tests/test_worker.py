"""Tests for the worker dispatcher (4.B1)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.worker import main as worker


def test_tick_writes_heartbeat(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    hb = tmp_path / "heartbeat"
    monkeypatch.setattr(worker, "HEARTBEAT_FILE", str(hb))
    now = datetime(2026, 6, 25, 12, 0, 0, tzinfo=UTC)
    worker.tick(now)
    assert hb.read_text() == str(int(now.timestamp()))


def test_boot_and_loop_runs_one_tick(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Boot on an in-memory DB (engine + schema + plugins) and run a single tick.
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

    from src.core import config as config_mod

    monkeypatch.setattr(config_mod, "CONFIG_PATH", str(cfg))
    monkeypatch.setattr(config_mod, "VERSION_PATH", str(ver))
    config_mod.get_settings.cache_clear()

    hb = tmp_path / "heartbeat"
    monkeypatch.setattr(worker, "HEARTBEAT_FILE", str(hb))

    worker._boot()
    worker._loop(tick_seconds=0, max_ticks=1)
    config_mod.get_settings.cache_clear()

    assert int(hb.read_text()) > 0
