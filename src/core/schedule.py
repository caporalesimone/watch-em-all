"""Scraper schedules (4.B2): per-scraper daily slots, stored and validated.

``times`` are wall-clock ``"HH:MM"`` entries in the installation timezone, kept sorted
and de-duplicated. The "due slot" logic (4.B3) builds on this.
"""

from __future__ import annotations

from datetime import datetime, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.models import ScraperSchedule


def parse_times(values: list[str]) -> list[str]:
    """Validate ``"HH:MM"`` entries; return them de-duplicated and sorted. Raises
    ``ValueError`` on a malformed or out-of-range entry."""
    seen: set[time] = set()
    parsed: list[time] = []
    for value in values:
        parts = value.split(":") if isinstance(value, str) else []
        if len(parts) != 2:
            raise ValueError(f"invalid time {value!r}; expected 'HH:MM'")
        try:
            slot = time(int(parts[0]), int(parts[1]))
        except ValueError as exc:
            raise ValueError(f"invalid time {value!r}; expected 'HH:MM'") from exc
        if slot not in seen:
            seen.add(slot)
            parsed.append(slot)
    parsed.sort()
    return [f"{t.hour:02d}:{t.minute:02d}" for t in parsed]


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
