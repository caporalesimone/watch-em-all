"""Per-scraper scrape-now routes (SCR-R15).

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

from src.core.errors import APIError
from src.core.plugins.base import ScraperPlugin
from src.core.plugins.context import build_context
from src.core.plugins.registry import LoadedPlugin
from src.core.scrape import CooldownStatus, claim_scrape, cooldown_status
from src.web.deps import SessionDep, UserDep

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

    def _run(user_id: int) -> None:
        ctx = build_context(manifest, plugin)
        try:
            plugin.run_for_user(ctx, user_id)
        except Exception:  # background task: log, never surface to a response
            log.exception("scrape-now failed for plugin %s user %s", plugin.plugin_id, user_id)
        finally:
            ctx.db.close()

    @router.post(
        "/scrape-now",
        response_model=ScrapeNowStarted,
        status_code=202,
        operation_id=f"{plugin.plugin_id}_scrape_now",
        summary="Run this scraper now for the current user (cooldown-limited).",
    )
    def scrape_now(user: UserDep, db: SessionDep, background: BackgroundTasks) -> ScrapeNowStarted:
        status = claim_scrape(db, plugin.plugin_id, user.sub)
        if not status.available:
            wait = _humanize(status.retry_after_seconds)
            raise APIError(
                429, "scrape_cooldown", f"Scrape now is on cooldown; available again in ~{wait}."
            )
        background.add_task(_run, user.sub)
        return ScrapeNowStarted(status="started", interval_seconds=status.interval_seconds)

    @router.get(
        "/scrape-now",
        response_model=ScrapeNowStatus,
        operation_id=f"{plugin.plugin_id}_scrape_now_status",
        summary="Cooldown status for the current user (drives the UI countdown).",
    )
    def scrape_now_status(user: UserDep, db: SessionDep) -> ScrapeNowStatus:
        return _to_model(cooldown_status(db, plugin.plugin_id, user.sub))

    return router
