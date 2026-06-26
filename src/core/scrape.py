"""Manual scrape-now cooldown (SCR-R15).

The scrape-now is a per-scraper, per-user manual trigger, rate-limited by a
minimum interval. This module owns the anchor logic, decoupled from the web: the
HTTP shell lives in ``src.web.routers.scrape`` and the per-scraper dispatch in
each scraper's ``run_for_user``.

The anchor (:class:`~src.core.models.ScrapeCooldown`) is the last scrape time per
``(plugin_id, user_id)``, written at the START of any scrape and read only by the
manual scrape-now (the asymmetry in SCR-R15). Phase 3 uses a constant interval;
phase 4 (4.B10) replaces it with the per-scraper reserved admin key
``scrape_now_min_interval_s``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.models import ScrapeCooldown
from src.core.plugins.base import ScraperPlugin

# Phase-3 mock (flow rule #7): a constant default; phase 4 makes it a per-scraper
# reserved admin key (scrape_now_min_interval_s) read from scraper_admin_config.
SCRAPE_NOW_COOLDOWN_SECONDS = 3600


@dataclass(frozen=True)
class CooldownStatus:
    """Whether a manual scrape is allowed now, and when it next will be."""

    available: bool
    available_at: datetime | None  # None when available now
    retry_after_seconds: int  # 0 when available now
    interval_seconds: int


def _as_utc(dt: datetime) -> datetime:
    """SQLite may return naive datetimes; treat a naive value as UTC."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _status(last: datetime | None, interval_seconds: int, now: datetime) -> CooldownStatus:
    if last is not None:
        available_at = _as_utc(last) + timedelta(seconds=interval_seconds)
        remaining = (available_at - now).total_seconds()
        if remaining > 0:
            return CooldownStatus(
                available=False,
                available_at=available_at,
                retry_after_seconds=math.ceil(remaining),
                interval_seconds=interval_seconds,
            )
    return CooldownStatus(
        available=True, available_at=None, retry_after_seconds=0, interval_seconds=interval_seconds
    )


def cooldown_status(
    session: Session,
    plugin_id: str,
    user_id: int,
    interval_seconds: int = SCRAPE_NOW_COOLDOWN_SECONDS,
) -> CooldownStatus:
    """Read-only: is a manual scrape available for this (plugin, user)? Drives the
    GET status endpoint and the UI countdown. Never writes."""
    row = session.scalar(
        select(ScrapeCooldown).where(
            ScrapeCooldown.plugin_id == plugin_id, ScrapeCooldown.user_id == user_id
        )
    )
    last = row.last_scraped_at if row is not None else None
    return _status(last, interval_seconds, datetime.now(UTC))


def claim_scrape(
    session: Session,
    plugin_id: str,
    user_id: int,
    interval_seconds: int = SCRAPE_NOW_COOLDOWN_SECONDS,
) -> CooldownStatus:
    """Atomically check the cooldown and, if available, stamp the anchor to *now*
    (at the START of the scrape) and commit. Returns the resulting status: when
    available it has already claimed the slot (a near-simultaneous second press
    then reads the fresh anchor and is refused); when not available it wrote
    nothing.
    """
    now = datetime.now(UTC)
    row = session.scalar(
        select(ScrapeCooldown).where(
            ScrapeCooldown.plugin_id == plugin_id, ScrapeCooldown.user_id == user_id
        )
    )
    status = _status(row.last_scraped_at if row is not None else None, interval_seconds, now)
    if not status.available:
        return status

    if row is None:
        session.add(ScrapeCooldown(plugin_id=plugin_id, user_id=user_id, last_scraped_at=now))
    else:
        row.last_scraped_at = now
    session.commit()
    return status


def stamp_cooldown(session: Session, plugin_id: str, user_id: int) -> None:
    """Write-only half of SCR-R15: stamp the anchor to *now* at the START of a scheduled
    scrape for this ``(plugin, user)``, so the user's manual scrape-now is then on
    cooldown. Never reads or blocks (a scheduled run is never itself rate-limited)."""
    now = datetime.now(UTC)
    row = session.scalar(
        select(ScrapeCooldown).where(
            ScrapeCooldown.plugin_id == plugin_id, ScrapeCooldown.user_id == user_id
        )
    )
    if row is None:
        session.add(ScrapeCooldown(plugin_id=plugin_id, user_id=user_id, last_scraped_at=now))
    else:
        row.last_scraped_at = now
    session.commit()


def implements_scraping(plugin: ScraperPlugin) -> bool:
    """True if the scraper actually implements ``run_for_user`` (overrides the
    base default). The web mounts the scrape-now route only for these, so a
    non-scraping test plugin gets no broken endpoint."""
    return type(plugin).run_for_user is not ScraperPlugin.run_for_user
