"""Health endpoint (1.B2, deployment.md). Public: app liveness + DB reachability."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from src.core.schedule import install_tz
from src.web.deps import SessionDep, SettingsDep
from src.web.schemas import HealthResponse

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness probe: app status, database reachability, and the product version (public).",
)
def health(response: Response, settings: SettingsDep, db: SessionDep) -> HealthResponse:
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except SQLAlchemyError:
        db_status = "down"
    if db_status != "ok":
        response.status_code = 503
    # Public liveness probe — no admin-only signals here. Schema drift (4.B0) is an
    # admin diagnostic, served by GET /api/admin/errors, never on this public probe.
    # worker heartbeat is informative and shared via the DB from phase 4; null here.
    return HealthResponse(
        status="ok" if db_status == "ok" else "degraded",
        db=db_status,
        version=settings.version,
        # Wall-clock in the installation TZ (serialised ISO8601 with offset) — the UI clock source.
        server_time=datetime.now(install_tz()),
        worker_heartbeat_age_s=None,
    )
