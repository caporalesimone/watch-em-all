"""Scrape run monitoring for the admin (10.B6).

The two questions this answers are *when did it run and how did it go* (the list) and *who
did it fail for* (the drill-down). Both read `scrape_run`/`scrape_user_log`, which the daily
maintenance prunes past `log_retention_days`: this is therefore a **recent window**, not a
history. The lifetime counters that do survive pruning are a separate endpoint (10.B20), and
the two must not be shown as if they answered the same question.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from src.core.errors import APIError
from src.core.models import ScrapeRun, ScrapeUserLog, User
from src.web.deps import AdminDep, SessionDep
from src.web.schemas import RunPage, RunSummary, RunUserDetail

router = APIRouter(prefix="/admin", tags=["Admin: runs"])


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
