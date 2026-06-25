"""Health endpoint (1.B2, deployment.md). Public: app liveness + DB reachability."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from src.web.deps import SessionDep, SettingsDep
from src.web.schemas import HealthResponse

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness probe: app status, database reachability, and the product version (public).",
)
def health(
    request: Request, response: Response, settings: SettingsDep, db: SessionDep
) -> HealthResponse:
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except SQLAlchemyError:
        db_status = "down"
    if db_status != "ok":
        response.status_code = 503
    # Schema drift (4.B0) is computed at startup and stashed on app.state; expose it
    # only when WEA_SCHEMA_DRIFT_ALERT is on (otherwise the field stays null).
    drift = getattr(request.app.state, "schema_drift", None)
    # worker heartbeat is informative and shared via the DB from phase 4; null here.
    return HealthResponse(
        status="ok" if db_status == "ok" else "degraded",
        db=db_status,
        version=settings.version,
        worker_heartbeat_age_s=None,
        schema_drift=drift if settings.schema_drift_alert else None,
    )
