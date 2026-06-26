"""Tests for the worker dispatcher + runner glue (4.B1–4.B4)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from src.core.contracts import DeltaCounters, Product
from src.core.db import Base
from src.core.models import ScrapeCooldown, ScraperSchedule, ScrapeRun, ScrapeUserLog
from src.core.plugins.base import ScraperPlugin
from src.core.plugins.context import PluginContext
from src.worker import main as worker


def _mem() -> tuple[Engine, Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine, Session(engine)


def test_heartbeat_writes_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    hb = tmp_path / "heartbeat"
    monkeypatch.setattr(worker, "HEARTBEAT_FILE", str(hb))
    now = datetime(2026, 6, 25, 12, 0, 0, tzinfo=UTC)
    worker._heartbeat(now)
    assert hb.read_text() == str(int(now.timestamp()))


def test_dispatch_due_submits_only_due_scrapers() -> None:
    engine, session = _mem()
    session.add(ScraperSchedule(scraper_id="due", times=["00:00"], enabled=True, last_slot=None))
    session.add(ScraperSchedule(scraper_id="off", times=["00:00"], enabled=False, last_slot=None))
    session.commit()
    submitted: list[str] = []

    def submit(scraper_id: str, slot: datetime, trigger: str) -> bool:
        submitted.append(scraper_id)
        return True

    worker.dispatch_due(session, datetime(2026, 6, 25, 12, 0, tzinfo=UTC), ZoneInfo("UTC"), submit)
    assert submitted == ["due"]
    session.close()
    engine.dispose()


class _FakeScraper(ScraperPlugin):
    plugin_id = "fake"
    table_metadata = None

    def __init__(self) -> None:
        self.users_run: list[int] = []

    def identity_seed(self, raw: object) -> str | None:
        return None

    def configured_users(self, context: PluginContext) -> list[int]:
        return [1, 2]

    def run_for_user(self, context: PluginContext, user_id: int) -> DeltaCounters:
        self.users_run.append(user_id)
        return DeltaCounters()


def test_run_scraper_iterates_users_stamps_cooldown_and_marks_slot() -> None:
    engine, session = _mem()
    session.add(ScraperSchedule(scraper_id="fake", times=["00:00"], enabled=True, last_slot=None))
    session.commit()
    slot = datetime(2026, 6, 25, 6, 0, tzinfo=UTC)
    fake = _FakeScraper()

    def _update_catalog(user_id: int, products: list[Product]) -> DeltaCounters:
        return DeltaCounters()

    ctx = PluginContext(
        engine=engine,
        db=session,
        logger=logging.getLogger("test.worker"),
        config={},
        update_catalog=_update_catalog,
    )
    worker._run_scraper(fake, ctx, "fake", slot)

    assert fake.users_run == [1, 2]
    pairs = {(c.plugin_id, c.user_id) for c in session.scalars(select(ScrapeCooldown))}
    assert pairs == {("fake", 1), ("fake", 2)}
    sched = session.get(ScraperSchedule, "fake")
    assert sched is not None and sched.last_slot is not None

    runs = list(session.scalars(select(ScrapeRun)))
    assert len(runs) == 1
    assert runs[0].status == "ok" and runs[0].users_processed == 2
    user_logs = list(session.scalars(select(ScrapeUserLog)))
    assert {u.user_id for u in user_logs} == {1, 2}
    assert all(u.status == "ok" for u in user_logs)
    session.close()
    engine.dispose()


def test_boot_and_loop_runs_one_tick(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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

    def submit(scraper_id: str, slot: datetime, trigger: str) -> bool:
        return True

    worker._boot()
    worker._loop(submit, max_ticks=1)
    config_mod.get_settings.cache_clear()

    assert int(hb.read_text()) > 0


def test_run_scraper_stops_at_deadline() -> None:
    engine, session = _mem()
    session.add(ScraperSchedule(scraper_id="fake", times=["00:00"], enabled=True, last_slot=None))
    session.commit()
    fake = _FakeScraper()

    def _update_catalog(user_id: int, products: list[Product]) -> DeltaCounters:
        return DeltaCounters()

    ctx = PluginContext(
        engine=engine,
        db=session,
        logger=logging.getLogger("test.worker"),
        config={},
        update_catalog=_update_catalog,
    )
    past = datetime(2000, 1, 1, tzinfo=UTC)
    worker._run_scraper(fake, ctx, "fake", datetime(2026, 6, 25, 6, 0, tzinfo=UTC), past)

    assert fake.users_run == []  # deadline already passed → no users processed
    sched = session.get(ScraperSchedule, "fake")
    assert sched is not None and sched.last_slot is not None  # slot still recorded (CRON-R6)
    runs = list(session.scalars(select(ScrapeRun)))
    assert len(runs) == 1 and runs[0].status == "timeout"
    assert list(session.scalars(select(ScrapeUserLog))) == []
    session.close()
    engine.dispose()
