"""Admin diagnostics (system) — admin-only signals.

Operational information the admin (and ONLY the admin) should see, kept off the
public ``/api/health`` probe so it never reaches a normal user or an anonymous
caller. First entry: the schema-drift report (4.B0), gated by
``WEA_SCHEMA_DRIFT_ALERT``. Future admin-facing errors land here too.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from src.core.schema_drift import SchemaDriftItem
from src.web.deps import AdminDep, SettingsDep

router = APIRouter(prefix="/admin", tags=["Admin: system"])


@router.get(
    "/schema-drift",
    response_model=list[SchemaDriftItem],
    summary="Schema drift found at startup (admin only; empty unless the alert is on).",
)
def schema_drift(
    request: Request, settings: SettingsDep, _admin: AdminDep
) -> list[SchemaDriftItem]:
    # The check always runs at startup and logs; this endpoint only EXPOSES it, and
    # only to an admin, when the alert is on.
    if not settings.schema_drift_alert:
        return []
    return list(getattr(request.app.state, "schema_drift", []))
