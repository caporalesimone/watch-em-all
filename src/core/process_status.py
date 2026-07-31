"""What each process reports about itself (PST-R1..R4).

The web and the worker share nothing but the database, so this table is how either says "I am
alive, and this is what I am doing" to the other — and to the admin looking at a page.

Two things are worth knowing before changing anything here.

**The row is updated in place.** A heartbeat is a state, not an event: the only question asked
of it is "is this process alive *now*", and the answer is the latest value. Appended it would be
one row per tick — ~525.000 a year at the default 60s, and 86.400 a *day* if someone lowers the
tick to its 1s floor for debugging — accumulated to answer a question that reads exactly one of
them, and then needing a retention policy of their own.

**The writer rate-limits itself** (PST-R2). The tick is a feature flag and its floor is 1s,
which is right for scheduling responsiveness and wrong for persistence: a developer lowering the
tick to watch something happen must not turn that into a write per second, for ever, on a row
whose readers tolerate minutes. So the beat and the tick are decoupled — a beat that comes too
soon is skipped, in memory, without touching the database.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.models import ProcessStatus

log = logging.getLogger("wea.core.process_status")

# The floor between two persisted beats (PST-R2). 30s is chosen against what reads it, not
# against what the database could survive: the container healthcheck calls the worker unhealthy
# at 180s, so this leaves 6x headroom and a skipped beat never reads as a fault, while nobody
# asks "is it alive" with sub-minute precision. It is also ~2.880 writes a day on one row, which
# is nothing — whereas the 1s tick floor would be 86.400.
MIN_HEARTBEAT_INTERVAL_S = 30.0

# The last beat this *process* actually wrote, so the rate limit costs no query. Per-process
# state in a module global is right here: it is a property of this running process, and a fresh
# one starting must beat immediately rather than inherit somebody else's timing.
_last_written: dict[str, float] = {}


@dataclass(frozen=True)
class Reported:
    """What a process last reported, as a reader sees it."""

    process: str
    last_seen_at: datetime
    state: str
    detail: str | None

    def age_s(self, now: datetime | None = None) -> float:
        """Seconds since this process last spoke. What "is it alive" is actually answered with."""
        reference = now or datetime.now(UTC)
        seen = (
            self.last_seen_at
            if self.last_seen_at.tzinfo is not None
            else self.last_seen_at.replace(tzinfo=UTC)
        )
        return max(0.0, (reference - seen).total_seconds())


def report(
    session: Session,
    process: str,
    *,
    state: str = "running",
    detail: str | None = None,
    monotonic: float | None = None,
    force: bool = False,
) -> bool:
    """Record that ``process`` is alive. Returns whether it actually wrote.

    Skipped when the previous write was less than :data:`MIN_HEARTBEAT_INTERVAL_S` ago, unless
    ``force`` — which a **change of state** uses, because "the worker suspended itself" is news
    and must not wait out a rate limit meant for a repetition.

    Never raises: a process must not die because it could not say that it is alive.
    """
    import time

    key = process
    stamp = monotonic if monotonic is not None else time.monotonic()
    previous = _last_written.get(key)
    if not force and previous is not None and (stamp - previous) < MIN_HEARTBEAT_INTERVAL_S:
        return False
    try:
        row = session.scalar(select(ProcessStatus).where(ProcessStatus.process == process))
        if row is None:
            row = ProcessStatus(process=process)
            session.add(row)
        row.last_seen_at = datetime.now(UTC)
        row.state = state
        row.detail = detail
        session.commit()
    except Exception:
        session.rollback()
        log.exception("process_status: could not report %s", process)
        return False
    _last_written[key] = stamp
    return True


def read(session: Session, process: str) -> Reported | None:
    """What ``process`` last reported, or ``None`` if it never has."""
    row = session.scalar(select(ProcessStatus).where(ProcessStatus.process == process))
    if row is None:
        return None
    return Reported(
        process=row.process, last_seen_at=row.last_seen_at, state=row.state, detail=row.detail
    )


def reset_rate_limit() -> None:
    """Forget this process's last-write timestamps. For tests, which need consecutive beats."""
    _last_written.clear()
