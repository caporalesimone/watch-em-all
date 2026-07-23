"""System log (4.B7, LOG-R1..R4): persist worker/scraper events to ``system_log`` and
read them back with a cursor.

Capture is automatic: a :class:`SystemLogHandler` attached to the ``wea`` logger persists
records from ``wea.worker.*`` (source ``worker``) and ``wea.plugin.*`` (source ``scraper``);
everything else (the web's own logs, libraries) stays on stdout only. The incremental
``id`` is the polling cursor (LOG-R3). Messages must never carry user operational content
(LOG-R4) — that discipline is on the caller. Writes use their own short-lived session so a
log line never touches the caller's transaction and never breaks a run.
"""

from __future__ import annotations

import logging

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from src.core.db import new_session
from src.core.models import SystemLog


def _source_for(logger_name: str) -> str | None:
    """Map a logger name to a LOG-R1 source, or ``None`` to skip (not persisted)."""
    if logger_name == "wea.worker" or logger_name.startswith("wea.worker."):
        return "worker"
    if logger_name.startswith("wea.plugin."):
        return "scraper"
    if logger_name == "wea.notifier" or logger_name.startswith("wea.notifier."):
        return "notifier"  # channel delivery (phase 7)
    if logger_name == "wea.alert" or logger_name.startswith("wea.alert."):
        return "alert"  # alert engine / dispatch (phase 7)
    return None


def _level_for(levelno: int) -> str | None:
    """Map a logging level number to our level string; below INFO is not persisted."""
    if levelno >= logging.ERROR:
        return "error"
    if levelno >= logging.WARNING:
        return "warning"
    if levelno >= logging.INFO:
        return "info"
    return None


class SystemLogHandler(logging.Handler):
    """Persists matching log records to ``system_log``. Never raises — a failed log write
    must not break a run, so every error is swallowed."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            source = _source_for(record.name)
            level = _level_for(record.levelno)
            if source is None or level is None:
                return
            context = getattr(record, "context", None)
            session = new_session()
            try:
                session.add(
                    SystemLog(
                        level=level,
                        source=source,
                        message=record.getMessage()[:2048],
                        context_json=context if isinstance(context, dict) else None,
                    )
                )
                session.commit()
            finally:
                session.close()
        except Exception:
            # Logging must never crash the caller; drop the row silently.
            pass


def install_system_log_handler() -> None:
    """Attach the DB handler to the ``wea`` logger once (idempotent). Records from
    ``wea.worker``/``wea.plugin`` then land in ``system_log`` in addition to stdout.

    Pins the ``wea`` logger to INFO so worker/scraper INFO events are captured regardless
    of the root configuration (e.g. test runners default the root to WARNING)."""
    logger = logging.getLogger("wea")
    if logger.level == logging.NOTSET or logger.level > logging.INFO:
        logger.setLevel(logging.INFO)
    if any(isinstance(h, SystemLogHandler) for h in logger.handlers):
        return
    handler = SystemLogHandler()
    handler.setLevel(logging.INFO)
    logger.addHandler(handler)


def _conditions(
    level: str | None, sources: list[str] | None, q: str | None
) -> list[ColumnElement[bool]]:
    """Shared WHERE conditions for the log reads (level / multi-source / message search)."""
    conds: list[ColumnElement[bool]] = []
    if level is not None:
        conds.append(SystemLog.level == level)
    if sources:
        conds.append(SystemLog.source.in_(sources))
    if q:
        conds.append(SystemLog.message.ilike(f"%{q}%"))
    return conds


def list_logs(
    session: Session,
    *,
    since: int | None = None,
    level: str | None = None,
    sources: list[str] | None = None,
    q: str | None = None,
    limit: int = 200,
) -> list[SystemLog]:
    """Cursor read (LOG-R3), for the live tail. ``since=None`` → the most recent ``limit``
    rows (returned ascending, for a first page); ``since=<id>`` → rows with ``id > since``
    ascending (the new ones). ``level``/``sources``/``q`` filters apply to both."""
    stmt = select(SystemLog)
    conds = _conditions(level, sources, q)
    if conds:
        stmt = stmt.where(*conds)
    if since is not None:
        return list(
            session.scalars(stmt.where(SystemLog.id > since).order_by(SystemLog.id).limit(limit))
        )
    # No cursor: the most recent N, then ascending so the client appends forward.
    recent = list(session.scalars(stmt.order_by(SystemLog.id.desc()).limit(limit)))
    return list(reversed(recent))


def page_logs(
    session: Session,
    *,
    page: int = 1,
    size: int = 50,
    level: str | None = None,
    sources: list[str] | None = None,
    q: str | None = None,
) -> tuple[list[SystemLog], int]:
    """Paged history read (newest first): one window of ``size`` rows at 1-based ``page``,
    plus the total count of all matching rows. Drives the page-number browser (Live off)."""
    conds = _conditions(level, sources, q)
    count_stmt = select(func.count()).select_from(SystemLog)
    rows_stmt = select(SystemLog)
    if conds:
        count_stmt = count_stmt.where(*conds)
        rows_stmt = rows_stmt.where(*conds)
    total = int(session.scalar(count_stmt) or 0)
    rows = list(
        session.scalars(
            rows_stmt.order_by(SystemLog.id.desc()).offset((page - 1) * size).limit(size)
        )
    )
    return rows, total


def level_counts(
    session: Session, *, sources: list[str] | None = None, q: str | None = None
) -> dict[str, int]:
    """Row count per level over the current source/search filters (the level filter itself
    is ignored, so the tabs can show how many of each level match)."""
    conds = _conditions(None, sources, q)
    stmt = select(SystemLog.level, func.count()).group_by(SystemLog.level)
    if conds:
        stmt = stmt.where(*conds)
    out = {"info": 0, "warning": 0, "error": 0}
    for row in session.execute(stmt).all():
        lvl = str(row[0])
        if lvl in out:
            out[lvl] = int(row[1])
    return out


def distinct_sources(session: Session) -> list[str]:
    """The distinct sources present in the log — drives the source filter chips (so they
    reflect what actually exists, e.g. worker/scraper today, notifier from phase 7)."""
    return sorted(s for s in session.scalars(select(SystemLog.source).distinct()) if s)
