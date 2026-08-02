"""Operational retention (MNT-R2, 4.B7): prune old system logs and run records beyond the
configured window (``log_retention_days``). Run once a day by the worker. Price history is
**never** pruned — it is the system's value (MNT-R2)."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from src.core.models import AlertLog, ScrapeRun, ScrapeUserLog, SystemLog


def purge_expired(session: Session, now: datetime, retention_days: int) -> dict[str, int]:
    """Delete ``system_log`` rows and ``scrape_run`` rows (with their ``scrape_user_log``
    children) older than the retention window. ``retention_days <= 0`` disables purging.
    Returns the per-table delete counts. Commits."""
    if retention_days <= 0:
        return {"system_log": 0, "scrape_run": 0}
    cutoff = now - timedelta(days=retention_days)
    # rowcount isn't on the typed Result; read it defensively via getattr.
    res_logs = session.execute(delete(SystemLog).where(SystemLog.created_at < cutoff))
    logs = getattr(res_logs, "rowcount", 0)
    # Remove the user-log children explicitly (don't rely on DB-level cascade, which is off
    # for SQLite), then the runs.
    old_runs = select(ScrapeRun.run_id).where(ScrapeRun.started_at < cutoff)
    session.execute(delete(ScrapeUserLog).where(ScrapeUserLog.run_id.in_(old_runs)))
    res_runs = session.execute(delete(ScrapeRun).where(ScrapeRun.started_at < cutoff))
    runs = getattr(res_runs, "rowcount", 0)
    session.commit()
    return {"system_log": int(logs or 0), "scrape_run": int(runs or 0)}


def purge_alerts_over_limit(session: Session, keep_last: int) -> int:
    """Trim every person's alert history to its most recent ``keep_last`` rows (10.B8b).

    **Counted, not aged**, which is a deliberate difference from the log and run retention
    beside it. Those measure operational noise, where "older than 90 days" is the right
    question. A person's notification history is not noise: a quiet month should not empty
    it, and a noisy week should not make it unreadable. A cap answers both.

    Per user, not globally: one heavy account would otherwise push everybody else's history
    out. ``keep_last <= 0`` disables the purge, the same "off" that ``log_retention_days``
    uses. Returns how many rows went. Commits.
    """
    if keep_last <= 0:
        return 0
    # The id is the tie-break, not just the sort: two digests written in the same second are
    # ordinary (one scrape can notify several people), and `created_at` alone would make the
    # cut-off ambiguous exactly where it matters. A window function does the per-user count
    # in one statement instead of a query per person.
    ranked = (
        select(
            AlertLog.id,
            func.row_number()
            .over(
                partition_by=AlertLog.user_id,
                order_by=(AlertLog.created_at.desc(), AlertLog.id.desc()),
            )
            .label("rank"),
        )
    ).subquery()
    over_limit = select(ranked.c.id).where(ranked.c.rank > keep_last)
    result = session.execute(delete(AlertLog).where(AlertLog.id.in_(over_limit)))
    session.commit()
    return int(getattr(result, "rowcount", 0) or 0)
