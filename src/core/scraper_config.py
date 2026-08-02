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
- ``http_retries``             ← ``http.DEFAULT_MAX_RETRIES`` (10.B22: the last politeness
  parameter that was still hard-wired)

Since 10.B22 the same ``config_json`` also holds the keys a **plugin** declares for itself
(:func:`plugin_config`). The two live side by side and may not collide: a declared key that
shadows a reserved one is refused at declaration, because the core reads reserved keys on the
plugin's behalf and a plugin quietly redefining one would change behaviour nobody asked it to.

``build_context`` reads these per run/scrape (HTTP client + scrape cache); the scrape-now
router reads ``scrape_now_min_interval_s`` for the manual cooldown.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.core.contracts import ConfigField
from src.core.http import DEFAULT_MAX_RETRIES, DEFAULT_MIN_INTERVAL_S, DEFAULT_TIMEOUT_S
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
    # The last hard-wired politeness knob (10.B22). Capped low on purpose: retries multiply
    # requests to a site that has already failed to answer, and a generous limit turns a bad
    # afternoon into a reason to be blocked.
    http_retries: int = Field(default=DEFAULT_MAX_RETRIES, ge=0, le=10)


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


# --------------------------------------------------------------- plugin-declared config (10.B22)


def declared_schema(plugin: object) -> list[ConfigField]:
    """The fields this scraper declares for itself, checked against the reserved keys.

    The collision guard is here rather than in a review comment: the core reads the reserved
    keys *on the plugin's behalf* — politeness, timeout, cache half-life — and a plugin that
    redefined one would be changing behaviour it does not own, in a way nobody reading either
    side would notice.
    """
    getter = getattr(plugin, "get_admin_config_schema", None)
    schema: list[ConfigField] = list(getter()) if callable(getter) else []
    clash = {f.key for f in schema} & RESERVED_KEYS
    if clash:
        raise ValueError(f"plugin config key(s) shadow a reserved key: {sorted(clash)}")
    return schema


def plugin_config(session: Session, plugin_id: str, schema: list[ConfigField]) -> dict[str, Any]:
    """Effective plugin-declared config: the schema's defaults overlaid with what is stored.

    Keys outside the schema are dropped on read as well as on write, so a field the plugin has
    since removed stops being handed to it without anybody having to clean the row.
    """
    try:
        row = session.get(ScraperAdminConfig, plugin_id)
    except SQLAlchemyError:
        session.rollback()
        row = None
    stored = dict(row.config_json) if row is not None else {}
    out: dict[str, Any] = {}
    for field in schema:
        out[field.key] = stored.get(field.key, field.default)
    return out


def set_plugin_config(
    session: Session, plugin_id: str, schema: list[ConfigField], incoming: dict[str, Any]
) -> dict[str, Any]:
    """Save the declared keys, leaving the reserved ones exactly where they were. Commits.

    Unknown keys are dropped rather than refused, the same rule the notifier side has had
    since 7.B3 (CFG-R5): the client renders the form from the schema, so anything else in the
    payload is a stale page, not an instruction.
    """
    allowed = {f.key: f for f in schema}
    row = session.get(ScraperAdminConfig, plugin_id)
    existing: dict[str, Any] = dict(row.config_json) if row is not None else {}
    for key, value in incoming.items():
        field = allowed.get(key)
        if field is None:
            continue
        existing[key] = _coerce(field, value)
    if row is None:
        session.add(ScraperAdminConfig(plugin_id=plugin_id, config_json=existing))
    else:
        row.config_json = existing
    session.commit()
    return plugin_config(session, plugin_id, schema)


def _coerce(field: ConfigField, value: Any) -> Any:
    """Bring a JSON value to the type the field declares. A form posts strings; a number that
    arrives as ``"5"`` and is stored as ``"5"`` compares wrong the first time somebody puts it
    in an arithmetic expression, and does so silently."""
    if value is None or value == "":
        return None
    if field.type == "number":
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return int(number) if number.is_integer() else number
    if field.type == "bool":
        return (
            value if isinstance(value, bool) else str(value).strip().lower() in ("1", "true", "yes")
        )
    return str(value)
