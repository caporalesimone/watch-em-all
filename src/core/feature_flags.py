"""Dev feature flags (4.B1a): admin-set, runtime, non-persistent.

A tiny key → JSON store in the DB so the web (which sets flags via the admin API) and
the worker (which reads them each tick) share the same values **across processes** — an
in-memory flag set on the web would never reach the separate worker container. The web
clears the table at startup, so flags are non-persistent: every boot reverts to the code
defaults in :data:`KNOWN_FLAGS`. Admin-only, dev-oriented — not a production toggle.
"""

from __future__ import annotations

import os
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.core.models import FeatureFlag


def _default_tick_seconds() -> int:
    try:
        return int(os.environ.get("WEA_TICK_SECONDS", "60"))
    except ValueError:
        return 60


# Known dev flags and their default value (the flag's params, a JSON object). GET lists
# these (default or overridden); only these keys may be set.
KNOWN_FLAGS: dict[str, dict[str, Any]] = {
    # Worker dispatcher tick interval — override to test scheduling without waiting.
    "worker_tick": {"seconds": _default_tick_seconds()},
}


def effective_flags(session: Session) -> dict[str, dict[str, Any]]:
    """Every known flag with its effective value (DB override merged over the default)."""
    overrides = {row.key: row.value for row in session.scalars(select(FeatureFlag))}
    return {key: {**default, **overrides.get(key, {})} for key, default in KNOWN_FLAGS.items()}


def set_flags(session: Session, partial: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Upsert one or more flag overrides (each merged over the current value). Unknown
    keys are rejected. Returns the new effective map."""
    unknown = set(partial) - set(KNOWN_FLAGS)
    if unknown:
        raise ValueError(f"unknown feature flag(s): {sorted(unknown)}")
    current = effective_flags(session)
    for key, value in partial.items():
        merged = {**current[key], **value}
        row = session.get(FeatureFlag, key)
        if row is None:
            session.add(FeatureFlag(key=key, value=merged))
        else:
            row.value = merged
    session.commit()
    return effective_flags(session)


def clear_flags(session: Session) -> None:
    """Drop all overrides → flags revert to the defaults (non-persistence at boot)."""
    session.execute(delete(FeatureFlag))
    session.commit()


def worker_tick_seconds(session: Session) -> int:
    """Effective worker tick interval (override or default), clamped to >= 1s."""
    value: Any = effective_flags(session)["worker_tick"].get("seconds")
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return _default_tick_seconds()
