"""Admin scraper scheduling (4.B2): read and set per-scraper slots.

Lists the loaded, schedulable scrapers (those that actually implement ``run_for_user``)
with their schedule, and lets the admin set the slots + enabled flag for one. The
dispatcher (4.B3+) reads these schedules to decide what is due.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field, ValidationError

from src.core import scrape_cache
from src.core.errors import APIError
from src.core.models import ScraperSchedule, ScraperStats
from src.core.plugins.base import ScraperPlugin
from src.core.plugins.registry import LoadedPlugin
from src.core.schedule import get_schedule, upsert_schedule
from src.core.scrape import implements_scraping
from src.core.scraper_config import ScraperReservedConfig, get_scraper_config, set_scraper_config
from src.core.scraper_stats import get_stats, reset_stats
from src.web.deps import AdminDep, SessionDep
from src.web.schemas import LifetimeStats

router = APIRouter(prefix="/admin", tags=["Admin: scrapers"])


class ScraperScheduleOut(BaseModel):
    scraper_id: str
    display_name: str
    times: list[str]
    enabled: bool
    last_slot: datetime | None
    cache_entries: int  # number of scrape_cache rows for this scraper (admin list)


class ScraperScheduleUpdate(BaseModel):
    times: list[str] = Field(default_factory=list)
    enabled: bool = True


class CacheCleared(BaseModel):
    deleted: int


def _schedulable(request: Request) -> dict[str, LoadedPlugin]:
    """Loaded scrapers that actually scrape (run_for_user implemented), keyed by id."""
    loaded: list[LoadedPlugin] = list(getattr(request.app.state, "loaded_plugins", []))
    return {
        lp.plugin.plugin_id: lp
        for lp in loaded
        if isinstance(lp.plugin, ScraperPlugin) and implements_scraping(lp.plugin)
    }


def _out(lp: LoadedPlugin, sched: ScraperSchedule | None, cache_entries: int) -> ScraperScheduleOut:
    return ScraperScheduleOut(
        scraper_id=lp.plugin.plugin_id,
        display_name=lp.manifest.display_name,
        times=sched.times if sched is not None else [],
        enabled=sched.enabled if sched is not None else True,
        last_slot=sched.last_slot if sched is not None else None,
        cache_entries=cache_entries,
    )


@router.get(
    "/scrapers",
    response_model=list[ScraperScheduleOut],
    summary="List schedulable scrapers with their schedule + cache size (admin only).",
)
def list_scrapers(request: Request, _admin: AdminDep, db: SessionDep) -> list[ScraperScheduleOut]:
    return [
        _out(lp, get_schedule(db, sid), scrape_cache.count(db, sid))
        for sid, lp in _schedulable(request).items()
    ]


@router.put(
    "/scrapers/{scraper_id}",
    response_model=ScraperScheduleOut,
    summary="Set a scraper's slots + enabled flag (admin only).",
)
def set_scraper(
    scraper_id: str,
    body: ScraperScheduleUpdate,
    request: Request,
    _admin: AdminDep,
    db: SessionDep,
) -> ScraperScheduleOut:
    lp = _schedulable(request).get(scraper_id)
    if lp is None:
        raise APIError(404, "not_found", f"no schedulable scraper {scraper_id!r}")
    try:
        sched = upsert_schedule(db, scraper_id, body.times, body.enabled)
    except ValueError as exc:
        raise APIError(422, "invalid_time", str(exc)) from exc
    return _out(lp, sched, scrape_cache.count(db, scraper_id))


@router.delete(
    "/scrapers/{scraper_id}/cache",
    response_model=CacheCleared,
    summary="Clear a scraper's scrape cache (admin only); returns how many entries were removed.",
)
def clear_scraper_cache(
    scraper_id: str,
    request: Request,
    _admin: AdminDep,
    db: SessionDep,
) -> CacheCleared:
    if scraper_id not in _schedulable(request):
        raise APIError(404, "not_found", f"no schedulable scraper {scraper_id!r}")
    return CacheCleared(deleted=scrape_cache.clear(db, scraper_id))


@router.get(
    "/scrapers/{scraper_id}/config",
    response_model=ScraperReservedConfig,
    summary="A scraper's core reserved config — effective values (admin only).",
)
def get_scraper_admin_config(
    scraper_id: str,
    request: Request,
    _admin: AdminDep,
    db: SessionDep,
) -> ScraperReservedConfig:
    if scraper_id not in _schedulable(request):
        raise APIError(404, "not_found", f"no schedulable scraper {scraper_id!r}")
    return get_scraper_config(db, scraper_id)


@router.patch(
    "/scrapers/{scraper_id}/config",
    response_model=ScraperReservedConfig,
    summary="Set one or more reserved config keys (admin only); returns the effective values.",
)
def set_scraper_admin_config(
    scraper_id: str,
    body: dict[str, Any],
    request: Request,
    _admin: AdminDep,
    db: SessionDep,
) -> ScraperReservedConfig:
    if scraper_id not in _schedulable(request):
        raise APIError(404, "not_found", f"no schedulable scraper {scraper_id!r}")
    try:
        return set_scraper_config(db, scraper_id, body)
    except (ValidationError, ValueError) as exc:
        raise APIError(422, "invalid_config", str(exc)) from exc


def _lifetime(row: ScraperStats) -> LifetimeStats:
    return LifetimeStats(
        plugin_id=row.plugin_id,
        since=row.since,
        runs_total=row.runs_total,
        runs_ok=row.runs_ok,
        runs_failed=row.runs_failed,
        runs_skipped_locked=row.runs_skipped_locked,
        consecutive_failures=row.consecutive_failures,
        last_run_at=row.last_run_at,
        last_success_at=row.last_success_at,
        last_failure_at=row.last_failure_at,
        http_requests_total=row.http_requests_total,
        cache_hits_total=row.cache_hits_total,
        bytes_downloaded_total=row.bytes_downloaded_total,
        politeness_wait_s_total=row.politeness_wait_s_total,
        run_seconds_total=row.run_seconds_total,
        rate_limited_total=row.rate_limited_total,
        gate_hits_total=row.gate_hits_total,
        gate_cleared_total=row.gate_cleared_total,
        robots_denied_total=row.robots_denied_total,
        products_delivered_total=row.products_delivered_total,
        pages_fetched_total=row.pages_fetched_total,
        parse_failures_total=row.parse_failures_total,
    )


@router.get(
    "/scrapers/{scraper_id}/lifetime-stats",
    response_model=LifetimeStats,
    summary="What this scraper has done since `since` — cumulative, survives log retention.",
)
def lifetime_stats(
    scraper_id: str, request: Request, _admin: AdminDep, db: SessionDep
) -> LifetimeStats:
    """The counters `scrape_run` cannot answer for, because that table is pruned (10.B20).

    A scraper that has never run still gets a row here, stamped now: `get_stats` creates it on
    first read, so the page shows honest zeros with a start date rather than a 404 that reads
    as *"this scraper does not exist"*.
    """
    if scraper_id not in _schedulable(request):
        raise APIError(404, "not_found", f"no schedulable scraper {scraper_id!r}")
    row = get_stats(db, scraper_id)
    db.commit()  # `get_stats` may have created the row
    return _lifetime(row)


@router.post(
    "/scrapers/{scraper_id}/lifetime-stats/reset",
    response_model=LifetimeStats,
    summary="Zero this scraper's lifetime counters and restamp `since` (admin only).",
)
def reset_lifetime_stats(
    scraper_id: str, request: Request, _admin: AdminDep, db: SessionDep
) -> LifetimeStats:
    """Destructive and without history (10.B21), which is the point: a cumulative that never
    resets lies after a configuration change — the politeness delay went from 1.5s to 11s in
    0.8.1, and totals either side of that are not comparable. The alternative was a caption
    explaining that the numbers mix two regimes, which asks the reader to do work a button
    does better. Nothing is archived: the new `since` is the whole record of when it happened.
    """
    if scraper_id not in _schedulable(request):
        raise APIError(404, "not_found", f"no schedulable scraper {scraper_id!r}")
    row = reset_stats(db, scraper_id)
    return _lifetime(row)
