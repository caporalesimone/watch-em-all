"""Core contracts shared between the scraper plugins and the core (product.md).

The boundary between a scraper and the core is exactly one type: every scraper
produces ``Product`` instances (via ``update_catalog``); the core never sees
anything else of the scraping. ``DeltaCounters`` is what the Catalog Update
Service returns for each delivery (CATSVC-R6).

These are plain Pydantic DTOs — not ORM rows. The persisted shape lives in
``src.core.models`` (``CatalogProduct`` / ``PriceHistory``); the Catalog Update
Service (``src.core.catalog``) maps from these DTOs to those rows.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class Product(BaseModel):
    """The current state of one product as a scraper sees it (product.md).

    Price/discount fields the scraper leaves as ``None`` are resolved by the
    core against the price history (PROD-R1); the scraper never knows the
    history. ``external_id`` is produced by the scraper base's identity
    template-method (SCR-R10), never hand-filled — but at the core boundary it
    is just a stable, unique string in the plugin's space.
    """

    plugin_id: str
    external_id: str  # stable across runs, unique within the plugin (product.md)
    url: str
    name: str
    image_url: str | None = None  # remote URL, never downloaded locally (PROD)

    price_current: Decimal  # discounted / current price
    price_original: Decimal | None = None  # None -> resolved from history, then current
    discount_pct: Decimal | None = None  # None -> computed from original/current
    currency: str = "EUR"  # ISO 4217; V1 neither converts nor aggregates currencies

    is_available: bool  # decided by the SCRAPER; never filtered out (PROD-R2)
    scraped_at: datetime
    extra: dict[str, Any] = Field(default_factory=dict)  # plugin-specific, persisted in extra_json


class DeltaCounters(BaseModel):
    """What ``update_catalog`` returns for one delivery (CATSVC-R6).

    Fed into the run record by the runner in later phases. ``found`` is the size
    of the delivered list; ``new``/``price_changes``/``removed`` are the deltas
    the service computed against the persisted catalog.
    """

    found: int = 0
    new: int = 0
    price_changes: int = 0
    removed: int = 0
