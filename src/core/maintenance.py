"""Operational retention (MNT-R2, 4.B7): prune old system logs and run records beyond the
configured window (``log_retention_days``). Run once a day by the worker. Price history is
**never** pruned — it is the system's value (MNT-R2)."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.core.models import ScrapeRun, ScrapeUserLog, SystemLog


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
