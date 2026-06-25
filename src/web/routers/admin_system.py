"""Admin diagnostics — admin-only errors and warnings.

A single generic feed of admin-facing problems (``GET /api/admin/errors``): each
entry is ``{source, type, title, description}``. Kept off the public ``/api/health``
probe — this information is for the admin only, never a normal user or an anonymous
caller. Sources plug in here; the first is the schema-drift check (4.B0). Future
operational problems (worker down, a plugin that failed to load, missing config, …)
add entries without a new endpoint.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel

from src.core.schema_drift import SchemaDriftItem
from src.web.deps import AdminDep, SettingsDep

router = APIRouter(prefix="/admin", tags=["Admin: system"])


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


@router.get(
    "/errors",
    response_model=list[AdminError],
    summary="Admin-facing errors and warnings (admin only; e.g. schema drift behind its flag).",
)
def admin_errors(request: Request, settings: SettingsDep, _admin: AdminDep) -> list[AdminError]:
    errors: list[AdminError] = []
    # Schema drift (4.B0): computed at startup, gated by WEA_SCHEMA_DRIFT_ALERT.
    if settings.schema_drift_alert:
        drift = list(getattr(request.app.state, "schema_drift", []))
        if drift:
            errors.append(_schema_drift_error(drift))
    return errors
