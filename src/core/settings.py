"""Global system settings (MNT-R3): runtime config with safe defaults.

Stored key → JSON in ``system_settings`` (persistent). Typed access merges the code
defaults with any stored overrides; unknown stored keys are ignored. Admin editing is a
later MVP (4.F2) — 4.B5 only reads ``scraper_run_timeout_min``.
"""

from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.models import SystemSetting


class SystemSettings(BaseModel):
    """Effective system settings (defaults from scheduling-models.md)."""

    scraper_run_timeout_min: int = 30
    catchup_warning_min: int = 10
    log_retention_days: int = 90
    user_deletion_retention_days: int = 30


def get_system_settings(session: Session) -> SystemSettings:
    """Defaults overlaid with any stored overrides (unknown keys ignored)."""
    known = set(SystemSettings.model_fields)
    overrides = {
        row.key: row.value for row in session.scalars(select(SystemSetting)) if row.key in known
    }
    return SystemSettings(**overrides)
