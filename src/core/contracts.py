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
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class AlertType(StrEnum):
    """The alert types a user can enable on a cart (alert-event.md). The position in the
    payload (a product's ``tags`` vs a cart's ``cart_events``) tells product tags from
    cart events apart; this single enum is the shared vocabulary of the alert engine.

    ``PRODUCT_ALL_TIME_LOW`` is intentionally absent in phase 6 — it depends on the price
    analytics capability, which lands in phase 11 (11.B5)."""

    # Product tags (valid inside ProductAlert.tags)
    PRODUCT_ON_SALE = "PRODUCT_ON_SALE"  # entered a discount, or dropped further while on sale
    PRODUCT_OFF_SALE = "PRODUCT_OFF_SALE"
    PRODUCT_UNAVAILABLE = "PRODUCT_UNAVAILABLE"
    PRODUCT_AVAILABLE_AGAIN = "PRODUCT_AVAILABLE_AGAIN"
    # Delisting is the end of the story, not an availability blip: the product left the
    # site's delivery altogether (9.B9). Emitted once, at the transition (ALERT-R12).
    PRODUCT_DELISTED = "PRODUCT_DELISTED"
    # Cart events (valid inside CartAlert.cart_events)
    CART_ALL_ON_SALE = "CART_ALL_ON_SALE"
    CART_THRESHOLD_REACHED = "CART_THRESHOLD_REACHED"
    CART_THRESHOLD_REACHED_PARTIAL = "CART_THRESHOLD_REACHED_PARTIAL"


class NotificationKind(StrEnum):
    """The kind of a notification, which also gives its category (alert-event.md). Phase 6
    writes only ``ALERT_DIGEST``; the summary (phase 11) and the admin/system text messages
    (phase 10) reuse the same ``alert_log`` and channel with a different payload."""

    ALERT_DIGEST = "alert_digest"  # diff vs baseline (category: system)
    SUMMARY = "summary"  # periodic snapshot (category: system)
    SYSTEM_MESSAGE = "system_message"  # core-generated text message (category: system)
    ADMIN_MESSAGE = "admin_message"  # admin-written text message (category: admin)


class ConfigField(BaseModel):
    """One declarative configuration field (config-field.md, CFG-R1..R6). Phase 7.

    A plugin describes its admin and user config as ``list[ConfigField]``; the core renders
    ONE dynamic form from the schema alone, without knowing the field names. ``label_key`` /
    ``help_key`` are **i18n keys** resolved in the plugin's frontend namespace (CFG-R2), never
    fixed text. Secret fields are masked and write-only (CFG-R3): the server never sends the
    value back, only an ``is_set`` flag. ``default`` must be typed coherently with ``type``
    (CFG-R6, e.g. ``587`` / ``True``, not strings). A ``password`` is always ``secret``."""

    key: str  # the key in the persisted config
    label_key: str  # translation KEY (plugin namespace), not fixed text
    type: Literal["text", "email", "password", "url", "number", "bool", "select"]
    required: bool = False
    secret: bool = False  # masked in the UI, write-only
    placeholder: str | None = None
    help_key: str | None = None  # translation key for the help text
    options: list[str] | None = None  # only for select
    default: str | int | bool | None = None  # coherent with type

    @model_validator(mode="after")
    def _password_is_secret(self) -> ConfigField:
        if self.type == "password":
            self.secret = True  # a password is always secret
        return self


class BrandRef(BaseModel):
    """A product's brand: a label plus an optional link (product.md PROD-R6).

    ``link`` (absolute URL to the brand page) is optional: the UI renders plain
    text, or clickable text opening a new tab when the link is present.
    """

    text: str
    link: str | None = None


class CategoryRef(BaseModel):
    """One breadcrumb step of a product's category (PROD-R7): a label + optional
    link. The full category is an ordered list, root → leaf."""

    text: str
    link: str | None = None


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
    brand: BrandRef | None = None  # text + optional link; None if not extracted (PROD-R6)
    # Generic product tags (e.g. "Edizione Limitata", "Pre Order"); the scraper
    # populates them from any source, the core only persists them (PROD-R5).
    tags: list[str] = Field(default_factory=list)
    # Category breadcrumb, root → leaf (PROD-R7); empty if the scraper has none.
    category: list[CategoryRef] = Field(default_factory=list)

    price_current: Decimal  # discounted / current price
    price_original: Decimal | None = None  # None -> resolved from history, then current
    discount_pct: Decimal | None = None  # None -> computed from original/current
    currency: str = "EUR"  # ISO 4217; V1 neither converts nor aggregates currencies

    is_available: bool  # decided by the SCRAPER; never filtered out (PROD-R2)
    # When the SITE produced this data, which is not always "now": a response served from
    # the scrape cache carries the timestamp of the fetch that filled it
    # (``HttpResponse.fetched_at``). The core stores it as ``last_seen_at``, so a scraper
    # that hardcodes ``now()`` here makes stale data look fresh.
    scraped_at: datetime
    extra: dict[str, Any] = Field(default_factory=dict)  # plugin-specific, persisted in extra_json


class Adjustment(BaseModel):
    """A correction on a **scraper_specific** cart total (adjustment.md), computed by
    the plugin's own rules. The core sums them without interpreting them.

    - ``id`` — the full i18n key the **frontend** renders into a localized label
      (e.g. ``"dragon_store.adjustments.threshold_discount"``).
    - ``params`` — values for that string's interpolation (e.g. ``{"pct": "10"}``).
    - ``description`` — human-readable, **debug only** (never shown to users).
    - ``amount`` — **signed**: POSITIVE = a saving (lowers the final estimate),
      NEGATIVE = an extra cost (raises it). ``final = discounted − Σ amount`` (ADJ-R2).
    """

    id: str
    description: str
    amount: Decimal
    params: dict[str, str] = Field(default_factory=dict)


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
