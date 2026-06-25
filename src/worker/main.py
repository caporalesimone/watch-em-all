"""Worker process (4.B1): the temporal dispatcher.

Replaces the phase-0 heartbeat stub. Boots like the web — engine, schema, plugins —
then runs a per-minute tick loop: each tick writes the heartbeat (the file the compose
healthcheck watches, CRON-R7) and runs ``tick(now)``, the seam where scheduling lands
(scrapers, then alerts/summary — 4.B2+). Single replica (CRON-R9). Runs as PID 1, so it
installs SIGTERM/SIGINT handlers to stop promptly on ``docker stop``.
"""

from __future__ import annotations

import logging
import os
import signal
import time
from datetime import UTC, datetime
from types import FrameType

from src.core.config import get_settings
from src.core.db import Base, create_schema, get_engine, init_engine, new_session
from src.core.feature_flags import worker_tick_seconds
from src.core.plugins.registry import load_plugins
from src.core.schema_drift import check_schema_drift

log = logging.getLogger("wea.worker")

HEARTBEAT_FILE = os.environ.get("WEA_HEARTBEAT_FILE", "/tmp/worker-heartbeat")


def _shutdown(signum: int, _frame: FrameType | None) -> None:
    log.info("worker: signal %s received, stopping", signum)
    raise SystemExit(0)


def _heartbeat(now: datetime) -> None:
    """Touch the heartbeat file with ``now`` (epoch seconds) — CRON-R7."""
    with open(HEARTBEAT_FILE, "w") as fh:
        fh.write(str(int(now.timestamp())))


def tick(now: datetime) -> None:
    """One dispatcher tick. Pure w.r.t. ``now`` (injected) so it stays testable.

    Today it only writes the heartbeat; the due-slot dispatch (scrapers to the serial
    runner, then alerts/summary) plugs in here in 4.B2+.
    """
    _heartbeat(now)


def _boot() -> None:
    """Bring up the same foundations as the web: engine, schema, plugins. Logs schema
    drift (4.B0) — the worker has no /api/health, so it only warns in the log."""
    settings = get_settings()
    init_engine(settings.core.database_url)
    create_schema()
    loaded = load_plugins(None)  # initialize plugins; the worker serves no HTTP
    metadatas = [Base.metadata] + [
        lp.plugin.table_metadata for lp in loaded if lp.plugin.table_metadata is not None
    ]
    try:
        for item in check_schema_drift(get_engine(), metadatas):
            if item.missing_table:
                log.warning("schema drift: table %r is missing from the database", item.table)
            else:
                log.warning(
                    "schema drift: table %r is missing column(s): %s",
                    item.table,
                    ", ".join(item.missing_columns),
                )
    except Exception:
        log.exception("schema-drift check failed")


def _current_tick_seconds() -> int:
    """The worker tick interval from the dev feature flag (override or default)."""
    session = new_session()
    try:
        return worker_tick_seconds(session)
    finally:
        session.close()


def _loop(max_ticks: int | None = None) -> None:
    """Tick forever (or ``max_ticks`` times, for tests), sleeping the flag-driven
    interval between ticks."""
    ticks = 0
    while max_ticks is None or ticks < max_ticks:
        tick(datetime.now(UTC))
        ticks += 1
        if max_ticks is None or ticks < max_ticks:
            time.sleep(_current_tick_seconds())


def run() -> None:
    logging.basicConfig(level=logging.INFO)
    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)
    _boot()
    log.info("worker started; heartbeat on %s (tick from feature flag)", HEARTBEAT_FILE)
    _loop()
