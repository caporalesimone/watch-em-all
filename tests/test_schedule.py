"""Tabular tests for the due-slot / catch-up logic (4.B3)."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from src.core.models import ScraperSchedule
from src.core.schedule import due_slot, latest_due_slot, parse_times

ROME = ZoneInfo("Europe/Rome")  # June → CEST (UTC+2)


def test_parse_times_dedupes_and_sorts() -> None:
    assert parse_times(["22:00", "06:00", "06:00"]) == ["06:00", "22:00"]


def test_parse_times_accepts_seconds() -> None:
    # HH:MM:SS accepted; seconds kept only when non-zero; sorted with second precision.
    assert parse_times(["23:10:30", "23:10", "23:10:00"]) == ["23:10", "23:10:30"]


def test_latest_due_slot_with_seconds() -> None:
    # 23:00:30 local has passed at 23:01 local → returned (21:00:30 UTC).
    now = datetime(2026, 6, 25, 21, 1, tzinfo=UTC)
    slot = latest_due_slot(["23:00:30"], now, ROME)
    assert slot == datetime(2026, 6, 25, 21, 0, 30, tzinfo=UTC)


def test_latest_due_slot_picks_most_recent_today() -> None:
    # 10:00 local (08:00 UTC) → most recent passed slot is today 06:00 local = 04:00 UTC.
    now = datetime(2026, 6, 25, 8, 0, tzinfo=UTC)
    slot = latest_due_slot(["06:00", "14:00", "22:00"], now, ROME)
    assert slot == datetime(2026, 6, 25, 4, 0, tzinfo=UTC)


def test_latest_due_slot_crosses_midnight() -> None:
    # 02:30 local, only slot 23:00 → yesterday's 23:00 local = 21:00 UTC on the 24th.
    now = datetime(2026, 6, 25, 0, 30, tzinfo=UTC)
    slot = latest_due_slot(["23:00"], now, ROME)
    assert slot == datetime(2026, 6, 24, 21, 0, tzinfo=UTC)


def test_latest_due_slot_none_when_empty() -> None:
    assert latest_due_slot([], datetime(2026, 6, 25, 8, 0, tzinfo=UTC), ROME) is None


def test_due_slot_respects_enabled_and_last_slot() -> None:
    now = datetime(2026, 6, 25, 8, 0, tzinfo=UTC)
    expected = datetime(2026, 6, 25, 4, 0, tzinfo=UTC)  # today 06:00 local

    enabled = ScraperSchedule(scraper_id="s", times=["06:00"], enabled=True, last_slot=None)
    assert due_slot(enabled, now, ROME) == expected

    suspended = ScraperSchedule(scraper_id="s", times=["06:00"], enabled=False, last_slot=None)
    assert due_slot(suspended, now, ROME) is None

    already_run = ScraperSchedule(scraper_id="s", times=["06:00"], enabled=True, last_slot=expected)
    assert due_slot(already_run, now, ROME) is None
