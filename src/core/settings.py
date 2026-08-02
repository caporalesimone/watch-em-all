"""Global system settings (MNT-R3): runtime config with safe defaults.

Stored key → JSON in ``system_settings`` (persistent). Typed access merges the code
defaults with any stored overrides; unknown stored keys are ignored. Admin editing is a
later MVP (4.F2) — 4.B5 only reads ``scraper_run_timeout_min``.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.models import SystemSetting


class SystemSettings(BaseModel):
    """Effective system settings (defaults from scheduling-models.md). Ranges keep an admin
    typo from breaking a run or the daily purge."""

    scraper_run_timeout_min: int = Field(default=30, ge=1, le=240)
    catchup_warning_min: int = Field(default=10, ge=0, le=1440)
    log_retention_days: int = Field(default=90, ge=0, le=3650)  # 0 = never purge
    user_deletion_retention_days: int = Field(default=30, ge=1, le=365)
    # How long a password may stand before the next sign-in forces a new one (10.B19).
    # **Fixed options, not free days**: an admin typing 3 instead of 30 would lock every
    # account into a change on their next visit, and the range check cannot tell the two
    # apart. 0 = never, which is the default — the feature is opt-in.
    password_expiry_days: Literal[0, 30, 90, 180, 365] = 0
    # The nightly maintenance window (10.B8a): the hour, in the install timezone, at which
    # every housekeeping job runs. One window rather than jobs scattered through the day, so
    # there is a single moment to look at when something did not get tidied — and a single
    # moment the machine is busy. Default 07:00, after the night's scrapes and before anybody
    # opens the page.
    maintenance_hour: int = Field(default=7, ge=0, le=23)
    # How many alerts each person keeps after the nightly purge (10.B8b). Counted, not aged:
    # a quiet month should not empty your history, and a noisy week should not make it
    # unreadable. 0 = keep everything, the same "off" that `log_retention_days` uses.
    alert_keep_last: int = Field(default=100, ge=0, le=100_000)


KNOWN_SETTINGS = set(SystemSettings.model_fields)


def get_system_settings(session: Session) -> SystemSettings:
    """Defaults overlaid with any stored overrides (unknown keys ignored)."""
    overrides = {
        row.key: row.value
        for row in session.scalars(select(SystemSetting))
        if row.key in KNOWN_SETTINGS
    }
    return SystemSettings(**overrides)


def set_system_settings(session: Session, partial: dict[str, Any]) -> SystemSettings:
    """Upsert one or more known settings (validated, ranges enforced); persists only the keys
    given. Unknown keys are rejected. Returns the new effective settings. Commits."""
    unknown = set(partial) - KNOWN_SETTINGS
    if unknown:
        raise ValueError(f"unknown setting(s): {sorted(unknown)}")
    validated = SystemSettings(**{**get_system_settings(session).model_dump(), **partial})
    for key in partial:
        value = getattr(validated, key)
        row = session.get(SystemSetting, key)
        if row is None:
            session.add(SystemSetting(key=key, value=value))
        else:
            row.value = value
    session.commit()
    return validated
