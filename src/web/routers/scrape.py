"""Per-scraper scrape-now routes (SCR-R15), restricted to super-users from 9.B8.

The web mounts a standard ``POST``/``GET`` ``…/scrape-now`` pair for every
scraper that implements ``run_for_user`` (``implements_scraping``), so the
cooldown + dispatch are uniform and a plugin never reimplements them. The route
lives in the web (not the core base) because it needs the authenticated user and
a request session — the core stays free of any web dependency.

``POST`` claims the cooldown slot (stamps the anchor at the start) and runs the
scrape in the background (no worker yet, phase 3); ``GET`` returns the cooldown
status that drives the UI countdown. The real write happens through the scraper's
``context.update_catalog`` inside ``run_for_user``.
"""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel

from src.core.db import get_engine
from src.core.errors import APIError
from src.core.locks import ScraperLock, acquire_scraper_lock
from src.core.plugins.base import ScraperPlugin
from src.core.plugins.context import build_context
from src.core.plugins.registry import LoadedPlugin
from src.core.scrape import CooldownStatus, claim_scrape, cooldown_status
from src.core.scraper_config import get_scraper_config
from src.web.adjust import run_user_alerts
from src.web.deps import SessionDep, SuperUserDep

log = logging.getLogger(__name__)


class ScrapeNowStatus(BaseModel):
    """Cooldown state for the current user (feeds the UI countdown)."""

    available: bool
    available_at: datetime | None
    retry_after_seconds: int
    interval_seconds: int


class ScrapeNowStarted(BaseModel):
    """202 body when a scrape was accepted."""

    status: str
    interval_seconds: int


def _to_model(s: CooldownStatus) -> ScrapeNowStatus:
    return ScrapeNowStatus(
        available=s.available,
        available_at=s.available_at,
        retry_after_seconds=s.retry_after_seconds,
        interval_seconds=s.interval_seconds,
    )


def _humanize(seconds: int) -> str:
    if seconds >= 3600:
        h, m = divmod(seconds // 60, 60)
        return f"{h}h {m}m" if m else f"{h}h"
    if seconds >= 60:
        return f"{seconds // 60}m"
    return f"{seconds}s"


def make_scrape_now_router(loaded: LoadedPlugin) -> APIRouter:
    """Build the scrape-now router for one scraper. Operation ids are namespaced
    by plugin so several scrapers do not collide in the OpenAPI schema."""
    router = APIRouter()
    plugin = loaded.plugin
    assert isinstance(plugin, ScraperPlugin)  # the web mounts this only for scrapers
    manifest = loaded.manifest

    def _run(lock: ScraperLock, user_id: int) -> None:
        ctx = build_context(manifest, plugin)
        try:
            plugin.run_for_user(ctx, user_id)
            # Event-driven alerts: right after the delivery, diff this user's carts and
            # write a digest if anything changed (no time-cadence).
            run_user_alerts(ctx.db, user_id)
        except Exception:  # background task: log, never surface to a response
            log.exception("scrape-now failed for plugin %s user %s", plugin.plugin_id, user_id)
        finally:
            ctx.db.close()
            lock.release()  # held since the request to keep the per-scraper lock (SCHED-R4)

    @router.post(
        "/scrape-now",
        response_model=ScrapeNowStarted,
        status_code=202,
        operation_id=f"{plugin.plugin_id}_scrape_now",
        summary="Run this scraper now for the current user (cooldown-limited).",
    )
    def scrape_now(
        user: SuperUserDep, db: SessionDep, background: BackgroundTasks
    ) -> ScrapeNowStarted:
        # SCHED-R4: refuse if a run (scheduled or manual) is already in progress; the lock
        # is held from here through the background task, which releases it when done.
        lock = acquire_scraper_lock(get_engine(), plugin.plugin_id)
        if lock is None:
            raise APIError(
                409, "scrape_in_progress", "A scrape for this source is already running."
            )
        interval = get_scraper_config(db, plugin.plugin_id).scrape_now_min_interval_s
        status = claim_scrape(db, plugin.plugin_id, user.sub, interval)
        if not status.available:
            lock.release()
            wait = _humanize(status.retry_after_seconds)
            raise APIError(
                429, "scrape_cooldown", f"Scrape now is on cooldown; available again in ~{wait}."
            )
        background.add_task(_run, lock, user.sub)
        return ScrapeNowStarted(status="started", interval_seconds=status.interval_seconds)

    @router.get(
        "/scrape-now",
        response_model=ScrapeNowStatus,
        operation_id=f"{plugin.plugin_id}_scrape_now_status",
        summary="Cooldown status for the current user (drives the UI countdown).",
    )
    def scrape_now_status(user: SuperUserDep, db: SessionDep) -> ScrapeNowStatus:
        interval = get_scraper_config(db, plugin.plugin_id).scrape_now_min_interval_s
        return _to_model(cooldown_status(db, plugin.plugin_id, user.sub, interval))

    return router
