"""Scraper schedules (4.B2): per-scraper daily slots, stored and validated.

``times`` are wall-clock ``"HH:MM"`` entries in the installation timezone, kept sorted
and de-duplicated. The "due slot" logic (4.B3) builds on this.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.models import ScraperSchedule


def _to_time(value: str) -> time:
    """Parse a ``"HH:MM"`` or ``"HH:MM:SS"`` wall-clock string. Raises ``ValueError``."""
    parts = value.split(":") if isinstance(value, str) else []
    if len(parts) not in (2, 3):
        raise ValueError(f"invalid time {value!r}; expected 'HH:MM' or 'HH:MM:SS'")
    try:
        hour, minute = int(parts[0]), int(parts[1])
        second = int(parts[2]) if len(parts) == 3 else 0
        return time(hour, minute, second)
    except ValueError as exc:
        raise ValueError(f"invalid time {value!r}; expected 'HH:MM' or 'HH:MM:SS'") from exc


def _fmt_time(t: time) -> str:
    """Canonical string: ``HH:MM`` on a whole minute, else ``HH:MM:SS``."""
    if t.second:
        return f"{t.hour:02d}:{t.minute:02d}:{t.second:02d}"
    return f"{t.hour:02d}:{t.minute:02d}"


def parse_times(values: list[str]) -> list[str]:
    """Validate ``"HH:MM"`` / ``"HH:MM:SS"`` entries; return them de-duplicated and
    sorted (seconds kept only when non-zero). Raises ``ValueError`` on a bad entry."""
    seen: set[time] = set()
    parsed: list[time] = []
    for value in values:
        slot = _to_time(value)
        if slot not in seen:
            seen.add(slot)
            parsed.append(slot)
    parsed.sort()
    return [_fmt_time(t) for t in parsed]


def get_schedule(session: Session, scraper_id: str) -> ScraperSchedule | None:
    return session.get(ScraperSchedule, scraper_id)


def list_schedules(session: Session) -> dict[str, ScraperSchedule]:
    return {row.scraper_id: row for row in session.scalars(select(ScraperSchedule))}


def upsert_schedule(
    session: Session, scraper_id: str, times: list[str], enabled: bool
) -> ScraperSchedule:
    """Set this scraper's slots + enabled flag (validates and normalises ``times``)."""
    clean = parse_times(times)
    row = session.get(ScraperSchedule, scraper_id)
    if row is None:
        row = ScraperSchedule(scraper_id=scraper_id, times=clean, enabled=enabled)
        session.add(row)
    else:
        row.times = clean
        row.enabled = enabled
    session.commit()
    return row


def set_last_slot(session: Session, scraper_id: str, slot: datetime) -> None:
    """Mark the last executed slot (CRON-R6: written even when the run errored)."""
    row = session.get(ScraperSchedule, scraper_id)
    if row is not None:
        row.last_slot = slot
        session.commit()


def install_tz() -> ZoneInfo:
    """The installation timezone (TZ env, default Europe/Rome). Slots are wall-clock
    in this zone; persisted timestamps stay UTC (BE-13)."""
    try:
        return ZoneInfo(os.environ.get("TZ", "Europe/Rome"))
    except Exception:
        return ZoneInfo("UTC")


def _as_utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes; treat a naive value as UTC."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def latest_due_slot(times: list[str], now: datetime, tz: ZoneInfo) -> datetime | None:
    """The most recent slot already passed (today or yesterday, in ``tz``), as a UTC
    datetime — or ``None`` if no slot has passed. Considering yesterday gives the
    cross-midnight catch-up (CRON-R2); only the single most recent slot is returned,
    never a replay of all missed ones."""
    if not times:
        return None
    now_local = now.astimezone(tz)
    today = now_local.date()
    passed: list[datetime] = []
    for entry in times:
        slot_time = _to_time(entry)
        for day in (today, today - timedelta(days=1)):
            local_dt = datetime.combine(day, slot_time, tzinfo=tz)
            if local_dt <= now_local:
                passed.append(local_dt)
    if not passed:
        return None
    return max(passed).astimezone(UTC)


def due_slot(schedule: ScraperSchedule, now: datetime, tz: ZoneInfo) -> datetime | None:
    """The slot this schedule is due for now (CRON-R2): the latest passed slot, if the
    schedule is enabled and that slot is newer than ``last_slot``. ``None`` otherwise."""
    if not schedule.enabled:
        return None
    slot = latest_due_slot(schedule.times, now, tz)
    if slot is None:
        return None
    if schedule.last_slot is not None and slot <= _as_utc(schedule.last_slot):
        return None
    return slot
