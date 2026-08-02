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
from datetime import UTC, date, datetime, timedelta
from types import FrameType
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.alert_engine import run_for_user
from src.core.cart_engine import AdjustmentFn
from src.core.config import get_settings
from src.core.contracts import DeltaCounters
from src.core.db import Base, create_schema, get_engine, init_engine, new_session
from src.core.feature_flags import effective_flags, worker_tick_seconds
from src.core.locks import scraper_lock
from src.core.maintenance import purge_alerts_over_limit, purge_expired
from src.core.models import Cart, ScraperSchedule
from src.core.notify import drain_deliveries, drain_message_deliveries, enqueue_deliveries
from src.core.plugins.base import NotifierPlugin, ScraperPlugin
from src.core.plugins.context import PluginContext, build_context
from src.core.plugins.registry import LoadedPlugin, load_plugins
from src.core.process_status import report
from src.core.run_log import close_run, open_run, run_one_user
from src.core.schedule import due_slot, install_tz, set_last_slot
from src.core.schema_drift import check_schema_drift
from src.core.scrape import implements_scraping, stamp_cooldown
from src.core.scrape_cache import purge_expired as purge_expired_cache
from src.core.scraper_stats import bump
from src.core.settings import get_system_settings
from src.core.system_log import install_system_log_handler
from src.core.user_purge import purge_due_users
from src.worker.runner import Runner

log = logging.getLogger("wea.worker")

HEARTBEAT_FILE = os.environ.get("WEA_HEARTBEAT_FILE", "/tmp/worker-heartbeat")

# Schedulable scrapers (scraper_id -> LoadedPlugin), populated at boot.
_loaded: dict[str, LoadedPlugin] = {}
# Every loaded plugin, for the account purge (10.B5), which must ask them all.
_all_plugins: list[LoadedPlugin] = []

# All loaded scraper plugins (scraper_id -> ScraperPlugin), for binding get_adjustments
# during alert runs — a scraper_specific cart's scraper may not be schedulable.
_scrapers: dict[str, ScraperPlugin] = {}

# All loaded notifier plugins, for enqueuing per-channel deliveries after a digest and draining
# the pending ones each tick (phase 7).
_notifiers: list[NotifierPlugin] = []

# Set at boot when the database schema does not match this version (INC-R4). While it is on,
# the tick heartbeats and does nothing else: everything else in it writes.
_incompatible: bool = False

# Submit a scraper run to the runner: (scraper_id, slot, trigger) -> enqueued?
Submit = Callable[[str, datetime, str], bool]


def _shutdown(signum: int, _frame: FrameType | None) -> None:
    log.info("worker: signal %s received, stopping", signum)
    raise SystemExit(0)


def _heartbeat(now: datetime) -> None:
    """Say that this worker is alive, twice over — CRON-R7 and PST-R1.

    The **file** is what the container's own healthcheck reads (``unhealthy`` past 180s), and it
    can only be that: it lives in the worker's own tmpfs, so nothing outside this container can
    see it. That is why `/api/health` reported `worker_heartbeat_age_s: null` from phase 1 until
    now — not because the worker was silent, but because the one place it spoke was unreachable.

    The **row** is the half the web can read. Rate-limited by `report` itself (PST-R2), so a tick
    lowered to its 1s floor for debugging does not become a write per second.
    """
    with open(HEARTBEAT_FILE, "w") as fh:
        fh.write(str(int(now.timestamp())))
    session = new_session()
    try:
        report(
            session,
            "worker",
            state="suspended" if _incompatible else "running",
            detail=(
                "the database schema does not match this version; scheduled work is suspended"
                if _incompatible
                else None
            ),
        )
    finally:
        session.close()


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
    # Every plugin, not just the schedulable scrapers: the account purge (10.B5) has to ask
    # each one to drop its rows, and a notifier with per-user tables is as relevant there as
    # a scraper is.
    _all_plugins.clear()
    _all_plugins.extend(loaded)
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
    global _incompatible
    _incompatible = False
    try:
        drift = check_schema_drift(get_engine(), metadatas)
        for item in drift:
            log.error("schema drift: %s", item.summary())
        if drift:
            # The web serves its incompatibility page (INC-R1); the worker's equivalent is to
            # do nothing, which is the only safe answer here. It has no user to explain
            # itself to, and unlike a page it *writes*: a scrape against a schema this
            # process does not agree with would fail halfway through a run, on a database
            # somebody may still be able to salvage.
            _incompatible = True
            # Forced past the rate limit: a change of state is news, not a repetition, and the
            # admin's errors feed should not have to wait half a minute to learn it (PST-R2).
            session = new_session()
            try:
                report(
                    session,
                    "worker",
                    state="suspended",
                    detail="the database schema does not match this version; "
                    "scheduled work is suspended",
                    force=True,
                )
            finally:
                session.close()
            log.error(
                "database incompatible with this version — scheduled work is suspended "
                "(no scrapes, no deliveries); the heartbeat continues so the web can see "
                "this worker is alive"
            )
    except Exception:
        log.exception("schema-drift check failed")
    session = new_session()
    try:
        log.info("feature flags: %s", effective_flags(session))
    finally:
        session.close()


def _maintenance_due(now: datetime, tz: ZoneInfo, hour: int, last_run: date | None) -> bool:
    """Has today's maintenance window opened, and not run yet? (10.B8a)

    Pure, so the decision is testable without a clock. Interpreted in the **install
    timezone** like the scraper slots (4.B3): "seven in the morning" has to mean the local
    seven. It catches up rather than skipping — a worker that was down at 07:00 and starts
    at 09:00 still tidies up today, because the alternative is a day of housekeeping quietly
    lost whenever the machine reboots at the wrong moment.
    """
    local = now.astimezone(tz)
    if last_run == local.date():
        return False
    return local.hour >= hour


def _maintenance(now: datetime) -> None:
    """The nightly housekeeping window (10.B8a): every scheduled job, in one place.

    One window rather than jobs scattered around the loop, so there is a single moment to
    look at when something did not get tidied — and a single moment the machine is busy.
    It **announces itself at both ends**: a maintenance that starts and never says it
    finished is the shape a hang has in a log, and without the closing line an admin cannot
    tell one from a quiet night. The end line is in a ``finally`` so it survives a failure.
    """
    log.info("maintenance window started")
    started = time.monotonic()
    try:
        _purge_operational_records(now)
        _purge_alert_history()
    finally:
        log.info("maintenance window finished in %.1fs", time.monotonic() - started)


def _purge_alert_history() -> None:
    """Trim each person's notification history to the configured length (10.B8b)."""
    try:
        session = new_session()
        try:
            keep = get_system_settings(session).alert_keep_last
            removed = purge_alerts_over_limit(session, keep)
        finally:
            session.close()
        if removed:
            log.info("alert retention: removed %d alert(s) beyond the last %d", removed, keep)
    except Exception:
        log.exception("alert retention failed")


def _purge_operational_records(now: datetime) -> None:
    """Prune old system logs and run records beyond ``log_retention_days`` (MNT-R2).
    A failure must never stop the worker, nor the jobs beside it in the window."""
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

    # Accounts whose grace period has expired (10.B5, CRON-R10). Its own try: an account
    # that will not delete must not take the log retention down with it, and vice versa.
    try:
        session = new_session()
        try:
            purged = purge_due_users(session, now, _all_plugins, _notifiers)
        finally:
            session.close()
        if purged:
            log.info("purged %d account(s) past their deletion deadline", purged)
    except Exception:
        log.exception("account purge failed")


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
    the caller can run the alert engine for them (event-driven alerts).

    The bookkeeping itself lives in :mod:`src.core.run_log` since 10.B20, shared with the
    manual path — what stays here is the scheduling: the deadline, the cooldown stamp, and
    the rule that one user's failure does not stop the queue.
    """
    run = open_run(ctx.db, scraper_id, trigger=trigger, slot=slot)
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

            def work(uid: int = user_id) -> DeltaCounters:
                # Inside the per-user slice, not before it: the cooldown stamp is a database
                # write like any other, and if it fails that is this user's problem, not a
                # reason to abandon everybody still in the queue (POOL-R5).
                stamp_cooldown(ctx.db, scraper_id, uid)
                return plugin.run_for_user(ctx, uid)

            outcomes.append(
                run_one_user(
                    ctx.db,
                    run,
                    user_id,
                    work,
                    http_before=(ctx.http.request_count, ctx.http.cache_hits),
                    http_after=lambda: (ctx.http.request_count, ctx.http.cache_hits),
                )
            )
    except Exception as exc:
        log.exception("scrape run failed: %s", scraper_id)
        run.error_message = str(exc)[:500]
    finally:
        close_run(
            ctx.db,
            run,
            outcomes,
            timed_out=timed_out,
            bytes_downloaded=ctx.http.bytes_downloaded,
            politeness_wait_s=ctx.http.waited_seconds,
            robots_denied=ctx.http.robots_denied,
        )
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
        # Both queues on the same step: an admin message is a notification like any other, and
        # giving it a timer of its own would only mean two things to keep in sync (10.B12).
        n = drain_deliveries(session, _notifiers) + drain_message_deliveries(session, _notifiers)
        if n:
            log.info("delivery drain: processed %d pending delivery(ies)", n)
    except Exception:
        session.rollback()
        log.exception("delivery drain failed")
    finally:
        session.close()


def _maintenance_hour() -> int:
    session = new_session()
    try:
        return get_system_settings(session).maintenance_hour
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
    last_maint_date: date | None = None
    ticks = 0
    while max_ticks is None or ticks < max_ticks:
        now = datetime.now(UTC)
        # Once a day, at the configured local hour (10.B8a). It used to run at the first
        # tick after midnight UTC, which meant "whenever the worker happened to restart" —
        # housekeeping at an hour nobody chose, and sometimes several times a day.
        if _maintenance_due(now, tz, _maintenance_hour(), last_maint_date):
            _maintenance(now)
            last_maint_date = now.astimezone(tz).date()
        _heartbeat(now)
        # The heartbeat still goes out while the schema is incompatible — it is how the web
        # knows this process is alive, and a silent worker would read as a second, different
        # fault. What is suspended is everything that would *write* through the mismatch.
        if not _incompatible:
            session = new_session()
            try:
                dispatch_due(session, now, tz, submit)
            finally:
                session.close()
            # Phase 7: drain pending channel deliveries, decoupled from scrape.
            _drain_deliveries_step()
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
