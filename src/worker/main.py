"""Worker process (4.B1–4.B4): the temporal dispatcher + serial runner.

Boots like the web (engine, schema, plugins), then ticks every interval: it writes the
heartbeat (CRON-R7) and dispatches **due** scraper slots (CRON-R2) to a serial runner —
one scraper at a time (SCHED-R6). The dispatcher itself never does long work (CRON-R5).
Single replica (CRON-R9). Runs as PID 1, so SIGTERM/SIGINT stop it promptly.
"""

from __future__ import annotations

import logging
import os
import signal
import time
from collections.abc import Callable
from datetime import UTC, datetime
from types import FrameType
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.config import get_settings
from src.core.db import Base, create_schema, get_engine, init_engine, new_session
from src.core.feature_flags import worker_tick_seconds
from src.core.models import ScraperSchedule
from src.core.plugins.base import ScraperPlugin
from src.core.plugins.context import PluginContext, build_context
from src.core.plugins.registry import LoadedPlugin, load_plugins
from src.core.schedule import due_slot, install_tz, set_last_slot
from src.core.schema_drift import check_schema_drift
from src.core.scrape import implements_scraping, stamp_cooldown
from src.worker.runner import Runner

log = logging.getLogger("wea.worker")

HEARTBEAT_FILE = os.environ.get("WEA_HEARTBEAT_FILE", "/tmp/worker-heartbeat")

# Schedulable scrapers (scraper_id -> LoadedPlugin), populated at boot.
_loaded: dict[str, LoadedPlugin] = {}

# Submit a scraper run to the runner: (scraper_id, slot, trigger) -> enqueued?
Submit = Callable[[str, datetime, str], bool]


def _shutdown(signum: int, _frame: FrameType | None) -> None:
    log.info("worker: signal %s received, stopping", signum)
    raise SystemExit(0)


def _heartbeat(now: datetime) -> None:
    """Touch the heartbeat file with ``now`` (epoch seconds) — CRON-R7."""
    with open(HEARTBEAT_FILE, "w") as fh:
        fh.write(str(int(now.timestamp())))


def _boot() -> None:
    """Bring up the same foundations as the web (engine, schema, plugins); cache the
    schedulable scrapers and log any schema drift (4.B0)."""
    settings = get_settings()
    init_engine(settings.core.database_url)
    create_schema()
    loaded = load_plugins(None)  # initialize plugins; the worker serves no HTTP
    _loaded.clear()
    for lp in loaded:
        if isinstance(lp.plugin, ScraperPlugin) and implements_scraping(lp.plugin):
            _loaded[lp.plugin.plugin_id] = lp
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


def _run_scraper(
    plugin: ScraperPlugin, ctx: PluginContext, scraper_id: str, slot: datetime
) -> None:
    """Run one scheduled scrape for every configured user, one at a time, stamping the
    manual-cooldown anchor (SCR-R15) per user. A per-user error doesn't stop the others
    (POOL-R5); the last slot is recorded even on failure (CRON-R6)."""
    try:
        for user_id in plugin.configured_users(ctx):
            try:
                stamp_cooldown(ctx.db, scraper_id, user_id)
                plugin.run_for_user(ctx, user_id)
            except Exception:
                log.exception("scrape failed: %s user %s", scraper_id, user_id)
    except Exception:
        log.exception("scrape run failed: %s", scraper_id)
    finally:
        set_last_slot(ctx.db, scraper_id, slot)


def scraper_job(scraper_id: str, slot: datetime, trigger: str = "scheduled") -> None:
    """Runner entry point: run one scraper (one Plugin Context per run)."""
    lp = _loaded.get(scraper_id)
    if lp is None:
        log.warning("runner: no schedulable scraper %r", scraper_id)
        return
    plugin = lp.plugin
    assert isinstance(plugin, ScraperPlugin)  # only scrapers are cached in _loaded
    ctx = build_context(lp.manifest, plugin)
    try:
        _run_scraper(plugin, ctx, scraper_id, slot)
    finally:
        ctx.db.close()


def dispatch_due(session: Session, now: datetime, tz: ZoneInfo, submit: Submit) -> None:
    """Submit every scraper that is due now (CRON-R2) to the runner."""
    for sched in session.scalars(select(ScraperSchedule)):
        slot = due_slot(sched, now, tz)
        if slot is not None:
            submit(sched.scraper_id, slot, "scheduled")


def _current_tick_seconds() -> int:
    session = new_session()
    try:
        return worker_tick_seconds(session)
    finally:
        session.close()


def _loop(submit: Submit, max_ticks: int | None = None) -> None:
    """Tick forever (or ``max_ticks`` times, for tests): heartbeat + dispatch due slots."""
    tz = install_tz()
    ticks = 0
    while max_ticks is None or ticks < max_ticks:
        now = datetime.now(UTC)
        _heartbeat(now)
        session = new_session()
        try:
            dispatch_due(session, now, tz, submit)
        finally:
            session.close()
        ticks += 1
        if max_ticks is None or ticks < max_ticks:
            time.sleep(_current_tick_seconds())


def run() -> None:
    logging.basicConfig(level=logging.INFO)
    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)
    _boot()
    runner = Runner(scraper_job)
    runner.start()
    log.info("worker started; heartbeat on %s (tick from feature flag)", HEARTBEAT_FILE)
    _loop(runner.submit)
