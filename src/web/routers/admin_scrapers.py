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
from src.core.models import ScraperSchedule
from src.core.plugins.base import ScraperPlugin
from src.core.plugins.registry import LoadedPlugin
from src.core.schedule import get_schedule, upsert_schedule
from src.core.scrape import implements_scraping
from src.core.scraper_config import ScraperReservedConfig, get_scraper_config, set_scraper_config
from src.web.deps import AdminDep, SessionDep

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
