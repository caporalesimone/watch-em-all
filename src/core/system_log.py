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

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.db import new_session
from src.core.models import SystemLog


def _source_for(logger_name: str) -> str | None:
    """Map a logger name to a LOG-R1 source, or ``None`` to skip (not persisted)."""
    if logger_name == "wea.worker" or logger_name.startswith("wea.worker."):
        return "worker"
    if logger_name.startswith("wea.plugin."):
        return "scraper"
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


def list_logs(
    session: Session,
    *,
    since: int | None = None,
    level: str | None = None,
    source: str | None = None,
    limit: int = 200,
) -> list[SystemLog]:
    """Cursor read (LOG-R3). ``since=None`` → the most recent ``limit`` rows (returned
    ascending, for a first page); ``since=<id>`` → rows with ``id > since`` ascending (the
    new ones). Optional ``level``/``source`` filters apply to both."""
    stmt = select(SystemLog)
    if level is not None:
        stmt = stmt.where(SystemLog.level == level)
    if source is not None:
        stmt = stmt.where(SystemLog.source == source)
    if since is not None:
        return list(
            session.scalars(stmt.where(SystemLog.id > since).order_by(SystemLog.id).limit(limit))
        )
    # No cursor: the most recent N, then ascending so the client appends forward.
    recent = list(session.scalars(stmt.order_by(SystemLog.id.desc()).limit(limit)))
    return list(reversed(recent))
