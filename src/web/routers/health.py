"""Health endpoint (1.B2, deployment.md). Public: app liveness + DB reachability."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from src.core.process_status import read as read_status
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
    # How long since the worker last said it was alive (PST-R3). Read from `process_status`,
    # which is the only thing the two processes share: the worker's other heartbeat is a file in
    # its own container's tmpfs, which is why this field was hardcoded `null` from phase 1 — the
    # worker was never silent, it just had nowhere to speak that the web could hear.
    # `null` now means only one thing: it has not reported since this database was created.
    heartbeat: float | None = None
    if db_status == "ok":
        try:
            reported = read_status(db, "worker")
            heartbeat = reported.age_s() if reported is not None else None
        except SQLAlchemyError:
            heartbeat = None  # a liveness probe does not fail over a secondary signal
    # Public liveness probe — no admin-only signals here. Schema drift (4.B0) is an
    # admin diagnostic, served by GET /api/admin/errors, never on this public probe. The
    # heartbeat's *age* is not a diagnostic of that kind: it says nothing about the inner
    # workings of the installation, only whether half of it is running.
    return HealthResponse(
        status="ok" if db_status == "ok" else "degraded",
        db=db_status,
        version=settings.version,
        # Wall-clock in the installation TZ (serialised ISO8601 with offset) — the UI clock source.
        server_time=datetime.now(install_tz()),
        worker_heartbeat_age_s=heartbeat,
    )
