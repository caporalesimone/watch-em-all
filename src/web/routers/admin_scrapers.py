"""Admin scraper scheduling (4.B2): read and set per-scraper slots.

Lists the loaded, schedulable scrapers (those that actually implement ``run_for_user``)
with their schedule, and lets the admin set the slots + enabled flag for one. The
dispatcher (4.B3+) reads these schedules to decide what is due.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from src.core.errors import APIError
from src.core.models import ScraperSchedule
from src.core.plugins.base import ScraperPlugin
from src.core.plugins.registry import LoadedPlugin
from src.core.schedule import get_schedule, upsert_schedule
from src.core.scrape import implements_scraping
from src.web.deps import AdminDep, SessionDep

router = APIRouter(prefix="/admin", tags=["Admin: scrapers"])


class ScraperScheduleOut(BaseModel):
    scraper_id: str
    display_name: str
    times: list[str]
    enabled: bool
    last_slot: datetime | None


class ScraperScheduleUpdate(BaseModel):
    times: list[str] = Field(default_factory=list)
    enabled: bool = True


def _schedulable(request: Request) -> dict[str, LoadedPlugin]:
    """Loaded scrapers that actually scrape (run_for_user implemented), keyed by id."""
    loaded: list[LoadedPlugin] = list(getattr(request.app.state, "loaded_plugins", []))
    return {
        lp.plugin.plugin_id: lp
        for lp in loaded
        if isinstance(lp.plugin, ScraperPlugin) and implements_scraping(lp.plugin)
    }


def _out(lp: LoadedPlugin, sched: ScraperSchedule | None) -> ScraperScheduleOut:
    return ScraperScheduleOut(
        scraper_id=lp.plugin.plugin_id,
        display_name=lp.manifest.display_name,
        times=sched.times if sched is not None else [],
        enabled=sched.enabled if sched is not None else True,
        last_slot=sched.last_slot if sched is not None else None,
    )


@router.get(
    "/scrapers",
    response_model=list[ScraperScheduleOut],
    summary="List schedulable scrapers with their schedule (admin only).",
)
def list_scrapers(request: Request, _admin: AdminDep, db: SessionDep) -> list[ScraperScheduleOut]:
    return [_out(lp, get_schedule(db, sid)) for sid, lp in _schedulable(request).items()]


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
    return _out(lp, sched)
