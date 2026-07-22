"""Alert cadence (alert-schedule.md, ALERT-R1..R3). Phase 6 (6.B7).

The per-user *when* of alerting: the weekdays and the time of day the alert engine runs.
Stored in ``alert_schedule``; the worker consults ``alert_due`` each tick and runs the
engine when a user is due, with same-day catch-up (like the scrapers' ``due_slot``). The
cadence off/on baseline transitions (ALERT-R3) are orchestrated by the API (6.B7).
"""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from src.core.models import AlertSchedule
from src.core.schedule import parse_times


def canonical_time(value: str) -> str:
    """Validate a ``"HH:MM"`` / ``"HH:MM:SS"`` wall-clock string and return it canonical
    ``"HH:MM:SS"``. Raises ``ValueError`` on a bad value (reuses the scraper-schedule parser)."""
    return parse_times([value])[0]


def normalize_weekdays(days: list[int]) -> list[int]:
    """Validate weekday integers (0=Monday … 6=Sunday), de-duplicate and sort. ``[]`` = off.
    Raises ``ValueError`` on an out-of-range value."""
    out = sorted({int(d) for d in days})
    for d in out:
        if d < 0 or d > 6:
            raise ValueError(f"weekday out of range (0..6): {d}")
    return out


def get_schedule(db: Session, user_id: int) -> AlertSchedule | None:
    return db.get(AlertSchedule, user_id)


def upsert_schedule(
    db: Session, user_id: int, scheduled_time: str, weekdays: list[int]
) -> AlertSchedule:
    """Set a user's cadence (validates/normalises the inputs). The caller commits and
    handles the baseline transition (delete on off, re-seed on on)."""
    st = canonical_time(scheduled_time)
    wd = normalize_weekdays(weekdays)
    row = db.get(AlertSchedule, user_id)
    if row is None:
        row = AlertSchedule(user_id=user_id, scheduled_time=st, weekdays=wd)
        db.add(row)
    else:
        row.scheduled_time = st
        row.weekdays = wd
    return row


def _as_time(value: str) -> time:
    hh, mm, ss = (int(part) for part in value.split(":"))
    return time(hh, mm, ss)


def alert_due(schedule: AlertSchedule, now: datetime, tz: ZoneInfo) -> bool:
    """Whether the engine is due for this user now (ALERT-R2): today is a configured
    weekday, the scheduled time has passed, and it has not already run today. The
    "not already today" check gives same-day catch-up if the worker was down at the time
    — a single run, never a backlog. ``weekdays == []`` (off) is never due."""
    if not schedule.weekdays:
        return False
    now_local = now.astimezone(tz)
    if now_local.weekday() not in schedule.weekdays:
        return False
    if now_local.time() < _as_time(schedule.scheduled_time):
        return False
    return schedule.last_run_date is None or schedule.last_run_date < now_local.date()
