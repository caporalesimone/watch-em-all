"""Unit tests for the alert cadence due-logic (phase 6.B7)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from src.core.alert_cadence import alert_due, canonical_time, normalize_weekdays
from src.core.models import AlertSchedule

TZ = ZoneInfo("Europe/Rome")


def _sched(
    *, weekdays: list[int], time: str = "09:00:00", last: date | None = None
) -> AlertSchedule:
    return AlertSchedule(user_id=1, scheduled_time=time, weekdays=weekdays, last_run_date=last)


# 2026-07-22 is a Wednesday (weekday 2). 07:00 UTC = 09:00 Europe/Rome (summer, +2).
WED_0900_LOCAL = datetime(2026, 7, 22, 7, 0, tzinfo=UTC)
WED_0800_LOCAL = datetime(2026, 7, 22, 6, 0, tzinfo=UTC)


def test_canonical_time_and_weekdays() -> None:
    assert canonical_time("9:00") == "09:00:00"
    assert canonical_time("09:30:15") == "09:30:15"
    assert normalize_weekdays([2, 0, 0, 6]) == [0, 2, 6]


def test_off_is_never_due() -> None:
    assert alert_due(_sched(weekdays=[]), WED_0900_LOCAL, TZ) is False


def test_due_on_configured_weekday_at_time() -> None:
    assert alert_due(_sched(weekdays=[2]), WED_0900_LOCAL, TZ) is True


def test_not_due_before_time() -> None:
    assert alert_due(_sched(weekdays=[2]), WED_0800_LOCAL, TZ) is False


def test_not_due_on_other_weekday() -> None:
    assert alert_due(_sched(weekdays=[0, 1]), WED_0900_LOCAL, TZ) is False


def test_same_day_catch_up() -> None:
    # Worker was down at 09:00; it's now later the same day and it hasn't run → still due.
    later = datetime(2026, 7, 22, 15, 0, tzinfo=UTC)
    assert alert_due(_sched(weekdays=[2]), later, TZ) is True


def test_not_due_if_already_ran_today() -> None:
    ran = date(2026, 7, 22)
    assert alert_due(_sched(weekdays=[2], last=ran), WED_0900_LOCAL, TZ) is False


def test_due_again_the_next_day() -> None:
    yesterday = date(2026, 7, 21)
    assert alert_due(_sched(weekdays=[2], last=yesterday), WED_0900_LOCAL, TZ) is True
