"""Scrape run monitoring for the admin (10.B6).

The two questions this answers are *when did it run and how did it go* (the list) and *who
did it fail for* (the drill-down). Both read `scrape_run`/`scrape_user_log`, which the daily
maintenance prunes past `log_retention_days`: this is therefore a **recent window**, not a
history. The lifetime counters that do survive pruning are a separate endpoint (10.B20), and
the two must not be shown as if they answered the same question.
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from datetime import date as date_type
from typing import Annotated, Literal

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from src.core.errors import APIError
from src.core.models import ScraperSchedule, ScrapeRun, ScrapeUserLog, User
from src.core.schedule import install_tz
from src.web.deps import AdminDep, SessionDep
from src.web.schemas import CalendarDay, CalendarSlot, RunPage, RunSummary, RunUserDetail

router = APIRouter(prefix="/admin", tags=["Admin: runs"])


def _as_utc(value: datetime) -> datetime:
    """SQLite gives naive timestamps back; everything written here is UTC."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _summary(run: ScrapeRun) -> RunSummary:
    return RunSummary(
        run_id=run.run_id,
        scraper_id=run.scraper_id,
        trigger=run.trigger,
        slot=run.slot,
        started_at=run.started_at,
        finished_at=run.finished_at,
        status=run.status,
        users_processed=run.users_processed,
        products_found=run.products_found,
        products_new=run.products_new,
        price_changes=run.price_changes,
        products_removed=run.products_removed,
        products_excluded=run.products_excluded,
        http_requests=run.http_requests,
        cache_hits=run.cache_hits,
        error_message=run.error_message,
    )


@router.get(
    "/runs",
    response_model=RunPage,
    summary="Recent scrape runs, newest first (admin only).",
)
def list_runs(
    _admin: AdminDep,
    db: SessionDep,
    scraper_id: str | None = None,
    status_filter: Annotated[
        Literal["ok", "partial", "error", "timeout", "running"] | None, Query(alias="status")
    ] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 25,
) -> RunPage:
    where = []
    if scraper_id:
        where.append(ScrapeRun.scraper_id == scraper_id)
    if status_filter:
        where.append(ScrapeRun.status == status_filter)

    total = db.scalar(select(func.count()).select_from(ScrapeRun).where(*where)) or 0
    # Newest first, and `run_id` as the tie-break: two runs can start in the same second
    # (a manual scrape next to a scheduled one), and a page boundary that lands between two
    # rows the database considers equal would show one of them twice.
    rows = db.scalars(
        select(ScrapeRun)
        .where(*where)
        .order_by(ScrapeRun.started_at.desc(), ScrapeRun.run_id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return RunPage(items=[_summary(r) for r in rows], total=int(total))


@router.get(
    "/runs/{run_id}",
    response_model=list[RunUserDetail],
    summary="Per-user detail of one run — who it failed for (admin only).",
)
def run_detail(run_id: int, _admin: AdminDep, db: SessionDep) -> list[RunUserDetail]:
    if db.get(ScrapeRun, run_id) is None:
        raise APIError(404, "run_not_found", "no such run")
    # Left join: a purged account leaves its rows behind (they key on a plain user_id, not a
    # foreign key), and dropping them would quietly change the arithmetic of a past run.
    rows = db.execute(
        select(ScrapeUserLog, User.username)
        .outerjoin(User, User.id == ScrapeUserLog.user_id)
        .where(ScrapeUserLog.run_id == run_id)
        # Failures first: on a `partial` run the whole reason to open this is to find them.
        .order_by((ScrapeUserLog.status == "ok").asc(), ScrapeUserLog.started_at.asc())
    ).all()
    return [
        RunUserDetail(
            user_id=row.ScrapeUserLog.user_id,
            username=row.username,
            started_at=row.ScrapeUserLog.started_at,
            finished_at=row.ScrapeUserLog.finished_at,
            status=row.ScrapeUserLog.status,
            products_found=row.ScrapeUserLog.products_found,
            products_new=row.ScrapeUserLog.products_new,
            price_changes=row.ScrapeUserLog.price_changes,
            http_requests=row.ScrapeUserLog.http_requests,
            cache_hits=row.ScrapeUserLog.cache_hits,
            error_message=row.ScrapeUserLog.error_message,
        )
        for row in rows
    ]


@router.get(
    "/scrapers/calendar",
    response_model=CalendarDay,
    summary="The runs planned for one day, with how long they usually take (admin only).",
)
def calendar(
    _admin: AdminDep,
    db: SessionDep,
    date: str | None = None,
) -> CalendarDay:
    """What the machine intends to do on a given day.

    Suspended scrapers are **returned and marked**, not filtered out: a day that looks empty
    because everything is switched off is indistinguishable from a day nothing was ever
    scheduled for, and those are very different problems.
    """
    try:
        day = date_type.fromisoformat(date) if date else datetime.now(tz=install_tz()).date()
    except ValueError as exc:
        raise APIError(422, "invalid_date", "date must be YYYY-MM-DD") from exc

    tz = install_tz()
    # Averaged in Python, not in SQL: the two dialects spell a timestamp difference
    # differently (`julianday` vs `extract(epoch ...)`), and the volume here is a fortnight of
    # runs — buying portability with a loop over a handful of rows is the right trade.
    # Only runs that **finished** count, and only the ones that went somewhere: an unfinished
    # row has no duration at all, and a timed-out one would drag the average towards the
    # failure instead of towards what the day normally costs.
    since = datetime.now(tz=UTC) - timedelta(days=14)
    durations: dict[str, list[float]] = {}
    for run in db.scalars(
        select(ScrapeRun).where(
            ScrapeRun.finished_at.is_not(None),
            ScrapeRun.started_at >= since,
            ScrapeRun.status.in_(("ok", "partial")),
        )
    ):
        assert run.finished_at is not None  # guarded by the query
        seconds = (_as_utc(run.finished_at) - _as_utc(run.started_at)).total_seconds()
        durations.setdefault(run.scraper_id, []).append(seconds)
    averages = {
        scraper: int(sum(values) / len(values)) for scraper, values in durations.items() if values
    }

    slots: list[CalendarSlot] = []
    for schedule in db.scalars(select(ScraperSchedule).order_by(ScraperSchedule.scraper_id)):
        for raw in schedule.times:
            # Stored canonically as HH:MM:SS since 4.F1, but HH:MM is still accepted there,
            # so both shapes have to survive a round trip through this endpoint.
            hh, mm, *rest = (int(part) for part in raw.split(":"))
            at = datetime.combine(day, time(hh, mm, rest[0] if rest else 0), tzinfo=tz)
            slots.append(
                CalendarSlot(
                    scraper_id=schedule.scraper_id,
                    at=at,
                    enabled=schedule.enabled,
                    avg_seconds=averages.get(schedule.scraper_id) or None,
                )
            )
    slots.sort(key=lambda s: (s.at, s.scraper_id))
    return CalendarDay(date=day.isoformat(), slots=slots)
