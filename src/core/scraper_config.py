"""Per-scraper admin config (PCFG-R2, 4.B10): the **core reserved keys** the core reads on
the plugin's behalf, stored per scraper in ``scraper_admin_config.config_json``.

Typed access merges the code defaults with any stored overrides; unknown stored keys are
ignored (so a future plugin-declared field sitting in the same ``config_json`` never breaks
the typed read). The defaults mirror the constants the values supersede — kept as a single
source so the two never drift:

- ``politeness_delay_ms``      ← ``http.DEFAULT_MIN_INTERVAL_S`` × 1000 (ms for finer granularity)
- ``http_timeout_s``           ← ``http.DEFAULT_TIMEOUT_S``
- ``cache_ttl_min``            ← ``scrape_cache.DEFAULT_CACHE_TTL_MIN`` (0 disables the cache)
- ``scrape_now_min_interval_s``← ``scrape.SCRAPE_NOW_COOLDOWN_SECONDS`` (retires the dev
  feature flag ``scrape_now_cooldown`` of 0.4.0)

``build_context`` reads these per run/scrape (HTTP client + scrape cache); the scrape-now
router reads ``scrape_now_min_interval_s`` for the manual cooldown.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.core.http import DEFAULT_MIN_INTERVAL_S, DEFAULT_TIMEOUT_S
from src.core.models import ScraperAdminConfig
from src.core.scrape import SCRAPE_NOW_COOLDOWN_SECONDS
from src.core.scrape_cache import DEFAULT_CACHE_TTL_MIN


class ScraperReservedConfig(BaseModel):
    """Effective core reserved config for one scraper (defaults from the superseded
    constants; ranges keep an admin typo from breaking a run)."""

    politeness_delay_ms: int = Field(default=round(DEFAULT_MIN_INTERVAL_S * 1000), ge=0, le=60_000)
    http_timeout_s: float = Field(default=DEFAULT_TIMEOUT_S, ge=1, le=120)
    cache_ttl_min: int = Field(default=DEFAULT_CACHE_TTL_MIN, ge=0, le=10_080)
    scrape_now_min_interval_s: int = Field(default=SCRAPE_NOW_COOLDOWN_SECONDS, ge=0, le=86_400)


RESERVED_KEYS = set(ScraperReservedConfig.model_fields)


def get_scraper_config(session: Session, plugin_id: str) -> ScraperReservedConfig:
    """Effective reserved config for a scraper: defaults overlaid with stored overrides
    (only the known reserved keys; anything else in ``config_json`` is ignored).

    Reading this must never break plugin load or a scrape: ``build_context`` calls it at
    ``initialize()`` too, where the config is unused. If the row can't be read (e.g. the
    ``scraper_admin_config`` table doesn't exist yet) it degrades to the safe defaults — in
    production the table is always created at startup, so this only bites isolated setups."""
    try:
        row = session.get(ScraperAdminConfig, plugin_id)
    except SQLAlchemyError:
        session.rollback()  # keep the caller's session usable after a failed read
        return ScraperReservedConfig()
    overrides: dict[str, Any] = (
        {k: v for k, v in (row.config_json or {}).items() if k in RESERVED_KEYS}
        if row is not None
        else {}
    )
    return ScraperReservedConfig(**overrides)


def set_scraper_config(
    session: Session, plugin_id: str, partial: dict[str, Any]
) -> ScraperReservedConfig:
    """Upsert one or more reserved keys (each merged over the current effective value),
    validating ranges. Unknown keys are rejected. Any non-reserved keys already in
    ``config_json`` (future plugin-declared fields) are preserved. Returns the new
    effective config. Commits."""
    unknown = set(partial) - RESERVED_KEYS
    if unknown:
        raise ValueError(f"unknown reserved config key(s): {sorted(unknown)}")
    merged = {**get_scraper_config(session, plugin_id).model_dump(), **partial}
    validated = ScraperReservedConfig(**merged)  # raises on out-of-range

    row = session.get(ScraperAdminConfig, plugin_id)
    existing: dict[str, Any] = dict(row.config_json) if row is not None else {}
    new_config = {**existing, **validated.model_dump()}
    if row is None:
        session.add(ScraperAdminConfig(plugin_id=plugin_id, config_json=new_config))
    else:
        row.config_json = new_config
    session.commit()
    return validated
