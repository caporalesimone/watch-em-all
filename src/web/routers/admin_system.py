"""Admin diagnostics — admin-only errors and warnings.

A single generic feed of admin-facing problems (``GET /api/admin/errors``): each
entry is ``{source, type, title, description}``. Kept off the public ``/api/health``
probe — this information is for the admin only, never a normal user or an anonymous
caller. Sources plug in here; the first is the schema-drift check (4.B0). Future
operational problems (worker down, a plugin that failed to load, missing config, …)
add entries without a new endpoint.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ValidationError

from src.core.errors import APIError
from src.core.feature_flags import effective_flags, set_flags
from src.core.models import SystemLog
from src.core.process_status import Reported
from src.core.process_status import read as read_status
from src.core.schema_drift import SchemaDriftItem
from src.core.settings import SystemSettings, get_system_settings, set_system_settings
from src.core.system_log import distinct_sources, level_counts, list_logs, page_logs
from src.web.deps import AdminDep, SessionDep, SettingsDep

router = APIRouter(prefix="/admin", tags=["Admin: system"])
log = logging.getLogger(__name__)


class AdminError(BaseModel):
    """One admin-facing problem. Copyable verbatim as ``{type, title, description}``."""

    source: str  # stable key of the producer, e.g. "schema_drift"
    type: Literal["error", "warning"]
    title: str
    description: str


def _describe_drift(item: SchemaDriftItem) -> str:
    if item.missing_table:
        return f"- {item.table}: table is missing"
    return f"- {item.table}: missing column(s) {', '.join(item.missing_columns)}"


def _schema_drift_error(drift: list[SchemaDriftItem]) -> AdminError:
    body = "\n".join(
        ["The database is missing tables/columns the code expects:", *map(_describe_drift, drift)]
    )
    return AdminError(
        source="schema_drift", type="error", title="Database schema drift", description=body
    )


# A worker that has not spoken for this long is reported (PST-R4). Deliberately the same
# threshold the container healthcheck uses, so the admin page and `docker ps` cannot disagree
# about whether the worker is up — two answers to one question is worse than a late answer.
_WORKER_SILENT_AFTER_S = 180


def _worker_error(reported: Reported | None) -> AdminError | None:
    """What the worker is failing to do, if anything. Three states worth telling an admin apart:
    it never reported, it stopped reporting, or it is reporting that it suspended itself."""
    if reported is None:
        return AdminError(
            source="worker_status",
            type="warning",
            title="The worker has never reported",
            description=(
                "Nothing has been scraped or delivered since this database was created. Either "
                "the worker has not started, or it cannot reach the database."
            ),
        )
    if reported.state == "suspended":
        return AdminError(
            source="worker_status",
            type="error",
            title="The worker has suspended itself",
            description=reported.detail or "No reason was recorded.",
        )
    age = reported.age_s()
    if age > _WORKER_SILENT_AFTER_S:
        return AdminError(
            source="worker_status",
            type="error",
            title="The worker has stopped reporting",
            description=(
                f"Last seen {int(age)}s ago. Scheduled scrapes and notification deliveries are "
                "not running."
            ),
        )
    return None


@router.get(
    "/errors",
    response_model=list[AdminError],
    summary="Admin-facing errors and warnings (admin only; e.g. schema drift behind its flag).",
)
def admin_errors(
    request: Request, settings: SettingsDep, db: SessionDep, _admin: AdminDep
) -> list[AdminError]:
    errors: list[AdminError] = []
    # Schema drift (4.B0): computed at startup, gated by WEA_SCHEMA_DRIFT_ALERT.
    if settings.schema_drift_alert:
        drift = list(getattr(request.app.state, "schema_drift", []))
        if drift:
            errors.append(_schema_drift_error(drift))
    # The worker (PST-R4). Not behind a flag: a worker that is not running means nothing gets
    # scraped and no notification goes out, which is a fault of the installation rather than a
    # development nicety — and the symptom on its own ("my prices are stale") points nowhere.
    worker = _worker_error(read_status(db, "worker"))
    if worker is not None:
        errors.append(worker)
    return errors


class SystemLogEntry(BaseModel):
    """One operational log row (LOG-R1..R4). ``id`` is the polling cursor."""

    id: int
    created_at: datetime
    level: Literal["info", "warning", "error"]
    source: str
    message: str
    context: dict[str, Any] | None = None


class SystemLogPage(BaseModel):
    """A page of history plus the stats that drive the filters (4.F3/F4)."""

    items: list[SystemLogEntry]
    total: int  # all rows matching the source/search/level filters
    counts: dict[str, int]  # rows per level over the source/search filters
    sources: list[str]  # distinct sources present, for the filter chips


def _entry(r: SystemLog) -> SystemLogEntry:
    return SystemLogEntry(
        id=r.id,
        created_at=r.created_at,
        level=r.level,  # type: ignore[arg-type]
        source=r.source,
        message=r.message,
        context=r.context_json,
    )


@router.get(
    "/logs",
    response_model=list[SystemLogEntry],
    summary="System log live tail (admin): cursor by id (no 'since' = latest N).",
)
def admin_logs(
    _admin: AdminDep,
    db: SessionDep,
    since: int | None = Query(None, description="rows with id > since (else the latest N)"),
    level: Literal["info", "warning", "error"] | None = Query(None),
    sources: Annotated[list[str] | None, Query(description="filter by source(s)")] = None,
    q: str | None = Query(None, description="case-insensitive substring on the message"),
    limit: int = Query(200, ge=1, le=1000),
) -> list[SystemLogEntry]:
    rows = list_logs(db, since=since, level=level, sources=sources, q=q, limit=limit)
    return [_entry(r) for r in rows]


@router.get(
    "/logs/page",
    response_model=SystemLogPage,
    summary="System log history, paged (admin): newest-first + total + counts + sources.",
)
def admin_logs_page(
    _admin: AdminDep,
    db: SessionDep,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=1000),
    level: Literal["info", "warning", "error"] | None = Query(None),
    sources: Annotated[list[str] | None, Query(description="filter by source(s)")] = None,
    q: str | None = Query(None, description="case-insensitive substring on the message"),
) -> SystemLogPage:
    rows, total = page_logs(db, page=page, size=size, level=level, sources=sources, q=q)
    return SystemLogPage(
        items=[_entry(r) for r in rows],
        total=total,
        counts=level_counts(db, sources=sources, q=q),
        sources=distinct_sources(db),
    )


@router.get(
    "/feature-flags",
    response_model=dict[str, dict[str, Any]],
    summary="Dev feature flags: effective values (defaults + overrides). Admin only.",
)
def get_feature_flags(_admin: AdminDep, db: SessionDep) -> dict[str, dict[str, Any]]:
    return effective_flags(db)


@router.patch(
    "/feature-flags",
    response_model=dict[str, dict[str, Any]],
    summary="Set one or more dev feature flags (known keys only); returns the effective map.",
)
def patch_feature_flags(
    body: dict[str, dict[str, Any]], _admin: AdminDep, db: SessionDep
) -> dict[str, dict[str, Any]]:
    try:
        result = set_flags(db, body)
    except ValueError as exc:
        raise APIError(422, "unknown_flag", str(exc)) from exc
    log.info("feature flags changed: %s", result)
    return result


@router.get(
    "/settings",
    response_model=SystemSettings,
    summary="System settings: effective values (defaults + overrides). Admin only.",
)
def get_settings(_admin: AdminDep, db: SessionDep) -> SystemSettings:
    return get_system_settings(db)


@router.patch(
    "/settings",
    response_model=SystemSettings,
    summary="Set one or more system settings (known keys only); returns the effective values.",
)
def patch_settings(body: dict[str, Any], _admin: AdminDep, db: SessionDep) -> SystemSettings:
    try:
        return set_system_settings(db, body)
    except (ValidationError, ValueError) as exc:
        raise APIError(422, "invalid_setting", str(exc)) from exc
