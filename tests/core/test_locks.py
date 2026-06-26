"""Tests for the per-scraper run lock (4.B5)."""

from __future__ import annotations

from sqlalchemy import create_engine

from src.core.locks import acquire_scraper_lock, scraper_lock


def test_lock_is_exclusive_then_reusable() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    a = acquire_scraper_lock(engine, "lock_a")
    assert a is not None
    assert acquire_scraper_lock(engine, "lock_a") is None  # already held
    other = acquire_scraper_lock(engine, "lock_b")
    assert other is not None  # different scraper → different lock
    other.release()
    a.release()
    reacquired = acquire_scraper_lock(engine, "lock_a")
    assert reacquired is not None  # reusable after release
    reacquired.release()


def test_scraper_lock_context_manager_releases() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with scraper_lock(engine, "lock_cm") as acquired:
        assert acquired is True
        assert acquire_scraper_lock(engine, "lock_cm") is None  # held inside the block
    again = acquire_scraper_lock(engine, "lock_cm")
    assert again is not None  # released on exit
    again.release()
