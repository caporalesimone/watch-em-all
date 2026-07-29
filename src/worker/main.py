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
from datetime import UTC, datetime, timedelta
from types import FrameType
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.alert_engine import run_for_user
from src.core.cart_engine import AdjustmentFn
from src.core.config import get_settings
from src.core.db import Base, create_schema, get_engine, init_engine, new_session
from src.core.feature_flags import effective_flags, worker_tick_seconds
from src.core.locks import scraper_lock
from src.core.maintenance import purge_expired
from src.core.models import Cart, ScraperSchedule, ScrapeRun, ScrapeUserLog
from src.core.notify import drain_deliveries, enqueue_deliveries
from src.core.plugins.base import NotifierPlugin, ScraperPlugin
from src.core.plugins.context import PluginContext, build_context
from src.core.plugins.registry import LoadedPlugin, load_plugins
from src.core.schedule import due_slot, install_tz, set_last_slot
from src.core.schema_drift import check_schema_drift
from src.core.scrape import implements_scraping, stamp_cooldown
from src.core.scrape_cache import purge_expired as purge_expired_cache
from src.core.scraper_stats import bump, record_run
from src.core.settings import get_system_settings
from src.core.system_log import install_system_log_handler
from src.worker.runner import Runner

log = logging.getLogger("wea.worker")

HEARTBEAT_FILE = os.environ.get("WEA_HEARTBEAT_FILE", "/tmp/worker-heartbeat")

# Schedulable scrapers (scraper_id -> LoadedPlugin), populated at boot.
_loaded: dict[str, LoadedPlugin] = {}

# All loaded scraper plugins (scraper_id -> ScraperPlugin), for binding get_adjustments
# during alert runs — a scraper_specific cart's scraper may not be schedulable.
_scrapers: dict[str, ScraperPlugin] = {}

# All loaded notifier plugins, for enqueuing per-channel deliveries after a digest and draining
# the pending ones each tick (phase 7).
_notifiers: list[NotifierPlugin] = []

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
    _scrapers.clear()
    _notifiers.clear()
    for lp in loaded:
        if isinstance(lp.plugin, ScraperPlugin):
            _scrapers[lp.plugin.plugin_id] = lp.plugin
            if implements_scraping(lp.plugin):
                _loaded[lp.plugin.plugin_id] = lp
        elif isinstance(lp.plugin, NotifierPlugin):
            _notifiers.append(lp.plugin)
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
    session = new_session()
    try:
        log.info("feature flags: %s", effective_flags(session))
    finally:
        session.close()


def _daily_maintenance(now: datetime) -> None:
    """Prune old system logs and run records beyond ``log_retention_days`` (MNT-R2).
    Runs once a day from the loop; a failure must never stop the worker."""
    try:
        session = new_session()
        try:
            days = get_system_settings(session).log_retention_days
            counts = purge_expired(session, now, days)
        finally:
            session.close()
        if counts["system_log"] or counts["scrape_run"]:
            log.info(
                "retention: purged %d log row(s), %d run(s) older than %d days",
                counts["system_log"],
                counts["scrape_run"],
                days,
            )
    except Exception:
        log.exception("daily maintenance failed")


def _aggregate_status(outcomes: list[str], timed_out: bool) -> str:
    """Run status from the per-user outcomes (scheduling-models.md)."""
    if timed_out:
        return "timeout"
    if not outcomes or all(o == "ok" for o in outcomes):
        return "ok"
    if any(o == "ok" for o in outcomes):
        return "partial"
    return "error"


def _run_scraper(
    plugin: ScraperPlugin,
    ctx: PluginContext,
    scraper_id: str,
    slot: datetime,
    deadline: datetime | None = None,
    trigger: str = "scheduled",
) -> set[int]:
    """Run one scheduled scrape for every configured user, one at a time, recording a
    ``scrape_run`` + a ``scrape_user_log`` per user with counters (4.B6). Stamps the
    manual-cooldown anchor (SCR-R15) per user; a per-user error doesn't stop the others
    (POOL-R5); a run past ``deadline`` stops between users (SCHED-R7); the last slot is
    recorded even on failure/timeout (CRON-R6). Returns the set of user ids processed, so
    the caller can run the alert engine for them (event-driven alerts)."""
    run = ScrapeRun(scraper_id=scraper_id, trigger=trigger, slot=slot, started_at=datetime.now(UTC))
    ctx.db.add(run)
    ctx.db.commit()
    outcomes: list[str] = []
    processed: set[int] = set()
    timed_out = False
    try:
        for user_id in plugin.configured_users(ctx):
            if deadline is not None and datetime.now(UTC) >= deadline:
                timed_out = True
                log.warning("scrape timed out: %s (slot %s)", scraper_id, slot)
                break
            processed.add(user_id)
            ulog = ScrapeUserLog(run_id=run.run_id, user_id=user_id, started_at=datetime.now(UTC))
            ctx.db.add(ulog)
            before = ctx.http.request_count
            before_hits = ctx.http.cache_hits
            try:
                stamp_cooldown(ctx.db, scraper_id, user_id)
                delta = plugin.run_for_user(ctx, user_id)
                ulog.products_found = delta.found
                ulog.products_new = delta.new
                ulog.price_changes = delta.price_changes
                run.products_removed += delta.removed
                ulog.status = "ok"
                outcomes.append("ok")
            except Exception as exc:
                log.exception("scrape failed: %s user %s", scraper_id, user_id)
                ulog.status = "error"
                ulog.error_message = str(exc)[:500]
                outcomes.append("error")
            ulog.http_requests = ctx.http.request_count - before
            ulog.cache_hits = ctx.http.cache_hits - before_hits
            ulog.finished_at = datetime.now(UTC)
            run.users_processed += 1
            run.products_found += ulog.products_found
            run.products_new += ulog.products_new
            run.price_changes += ulog.price_changes
            run.http_requests += ulog.http_requests
            run.cache_hits += ulog.cache_hits
            ctx.db.commit()
    except Exception as exc:
        log.exception("scrape run failed: %s", scraper_id)
        run.error_message = str(exc)[:500]
    finally:
        run.status = _aggregate_status(outcomes, timed_out)
        run.finished_at = datetime.now(UTC)
        ctx.db.commit()
        # Lifetime statistics (9.B6c): scrape_run has retention, so this row is the only
        # memory of what this scraper has ever done. Never let it break a run.
        try:
            record_run(
                ctx.db,
                scraper_id,
                ok=run.status == "ok",
                seconds=(run.finished_at - run.started_at).total_seconds(),
                http_requests=run.http_requests,
                cache_hits=run.cache_hits,
                bytes_downloaded=ctx.http.bytes_downloaded,
                politeness_wait_s=ctx.http.waited_seconds,
                robots_denied=ctx.http.robots_denied,
                products_delivered=run.products_found,
            )
        except Exception:
            log.exception("could not record the lifetime statistics of %s", scraper_id)
        set_last_slot(ctx.db, scraper_id, slot)
        log.info(
            "run %s (%s): %s — %d user(s), found=%d new=%d price_changes=%d removed=%d "
            "http=%d cache=%d",
            scraper_id,
            trigger,
            run.status,
            run.users_processed,
            run.products_found,
            run.products_new,
            run.price_changes,
            run.products_removed,
            run.http_requests,
            run.cache_hits,
        )
    return processed


def scraper_job(scraper_id: str, slot: datetime, trigger: str = "scheduled") -> None:
    """Runner entry point: run one scraper (one Plugin Context per run), under the
    per-scraper lock (SCHED-R4) and the run timeout (SCHED-R7)."""
    lp = _loaded.get(scraper_id)
    if lp is None:
        log.warning("runner: no schedulable scraper %r", scraper_id)
        return
    plugin = lp.plugin
    assert isinstance(plugin, ScraperPlugin)  # only scrapers are cached in _loaded
    with scraper_lock(get_engine(), scraper_id) as acquired:
        if not acquired:
            log.warning("runner: %s already running, slot %s skipped", scraper_id, slot)
            session = new_session()
            try:
                bump(session, scraper_id, {"runs_skipped_locked": 1})
            except Exception:
                log.exception("could not record the skipped run of %s", scraper_id)
            finally:
                session.close()
            return
        log.info("running %s (slot %s, %s)", scraper_id, slot, trigger)
        ctx = build_context(lp.manifest, plugin)
        try:
            purge_expired_cache(ctx.db, scraper_id)  # POOL-R3: drop expired cache before the run
            timeout_min = get_system_settings(ctx.db).scraper_run_timeout_min
            deadline = datetime.now(UTC) + timedelta(minutes=timeout_min)
            processed = _run_scraper(plugin, ctx, scraper_id, slot, deadline)
            # Event-driven alerts: right after the scrape, run the alert engine for the
            # users it touched (one aggregated digest each; no time-cadence).
            _run_alerts_for_users(ctx.db, processed)
        finally:
            ctx.db.close()


def dispatch_due(session: Session, now: datetime, tz: ZoneInfo, submit: Submit) -> None:
    """Submit every scraper that is due now (CRON-R2) to the runner."""
    for sched in session.scalars(select(ScraperSchedule)):
        slot = due_slot(sched, now, tz)
        if slot is not None and submit(sched.scraper_id, slot, "scheduled"):
            log.info("scheduled run due: %s (slot %s) → queued", sched.scraper_id, slot)


def _alert_adjuster(cart: Cart) -> AdjustmentFn | None:
    """Bind a scraper_specific cart's ``get_adjustments`` from the loaded plugins."""
    if cart.mode != "scraper_specific" or cart.scraper_id is None:
        return None
    plugin = _scrapers.get(cart.scraper_id)
    return plugin.get_adjustments if plugin is not None else None


def _run_alerts_for_users(session: Session, user_ids: set[int]) -> None:
    """Run the alert engine for each user a scrape just touched (event-driven alerts): at
    most one aggregated digest per user, written to the history. A per-user failure is
    logged and never blocks the others; nothing runs on cadence any more."""
    for user_id in sorted(user_ids):
        try:
            result = run_for_user(session, user_id, _alert_adjuster)
            if result is not None:
                enqueue_deliveries(session, result, _notifiers)  # per-channel rows; in-app inline
                log.info("alert digest written for user %s (alert_log %s)", user_id, result.id)
        except Exception:
            session.rollback()
            log.exception("alert run failed for user %s", user_id)


def _drain_deliveries_step() -> None:
    """Periodic worker step (phase 7): send the pending network deliveries and record outcomes.
    Decoupled from the scrape so a slow/failing channel never blocks a run. Never raises."""
    session = new_session()
    try:
        n = drain_deliveries(session, _notifiers)
        if n:
            log.info("delivery drain: processed %d pending delivery(ies)", n)
    except Exception:
        session.rollback()
        log.exception("delivery drain failed")
    finally:
        session.close()


def _current_tick_seconds() -> int:
    session = new_session()
    try:
        return worker_tick_seconds(session)
    finally:
        session.close()


def _loop(submit: Submit, max_ticks: int | None = None) -> None:
    """Tick forever (or ``max_ticks`` times, for tests): heartbeat + dispatch due slots."""
    tz = install_tz()
    last_interval: int | None = None
    last_maint_date = None
    ticks = 0
    while max_ticks is None or ticks < max_ticks:
        now = datetime.now(UTC)
        if now.date() != last_maint_date:  # once per (UTC) day, and at the first tick
            _daily_maintenance(now)
            last_maint_date = now.date()
        _heartbeat(now)
        session = new_session()
        try:
            dispatch_due(session, now, tz, submit)
        finally:
            session.close()
        _drain_deliveries_step()  # phase 7: drain pending channel deliveries, decoupled from scrape
        ticks += 1
        if max_ticks is not None and ticks >= max_ticks:
            break
        # Wait for the next tick, re-reading the (runtime-overridable) interval every
        # second — so a feature-flag change takes effect within ~1s, not only after the
        # previous interval has elapsed.
        while True:
            interval = _current_tick_seconds()
            if interval != last_interval:
                log.info("worker tick interval: %ss", interval)
                last_interval = interval
            if (datetime.now(UTC) - now).total_seconds() >= interval:
                break
            time.sleep(1)


def run() -> None:
    logging.basicConfig(level=logging.INFO)
    install_system_log_handler()  # worker/scraper logs -> system_log (4.B7), plus stdout
    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)
    _boot()
    runner = Runner(scraper_job)
    runner.start()
    log.info(
        "worker started, version %s; heartbeat on %s (tick from feature flag)",
        get_settings().version,
        HEARTBEAT_FILE,
    )
    try:
        _loop(runner.submit)
    finally:
        # `_shutdown` announces the signal; this announces that the loop actually left. The
        # pair is what tells a stop apart from a crash — and a `finally` catches both, since
        # the signal handler stops the process by raising SystemExit through the loop.
        log.info("worker stopped")
