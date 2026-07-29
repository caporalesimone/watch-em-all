"""SQLAlchemy models. Phase 1 introduces the `users` table (schema.md, Auth);
phase 3 adds the catalog and its history (`products` / `price_history`).

Columns mirror the schema doc in full (including the deletion/last-login fields
used from phase 10) so the table is created once and grows only additively.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.core.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    # Every account has a first and last name, both required (USR); stored here so
    # the UI can greet/display the person rather than the login handle.
    first_name: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    last_name: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    deletion_marked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deletion_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locale: Mapped[str] = mapped_column(String(8), nullable=False, default="en")
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    refresh_jti: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CatalogProduct(Base):
    """A product in a user's catalog (schema.md, "Catalogo e storico").

    Identity is ``(user_id, plugin_id, external_id)`` — the UNIQUE the Catalog
    Update Service matches on (CATSVC-R2). Price/discount are stored already
    resolved (the service fills them per the Product contract before writing).
    Per-user (DB-R1): every query filters by the token's user.
    """

    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("user_id", "plugin_id", "external_id", name="uq_products_identity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plugin_id: Mapped[str] = mapped_column(String(64), nullable=False)
    external_id: Mapped[str] = mapped_column(String(64), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    # Brand: label + optional link (PROD-R6). Two columns rather than a blob so the
    # UI can render a (clickable) brand without unpacking JSON; both nullable.
    brand_text: Mapped[str | None] = mapped_column(String(256), nullable=True)
    brand_link: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    # Generic product tags (PROD-R5): a JSON array of strings, persisted as-is.
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    # Category breadcrumb (PROD-R7): JSON array of {text, link}, root → leaf.
    category: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    # Plugin-specific data (DB-R3: Decimal as string, datetime ISO-8601 UTC inside).
    extra_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")
    price_current: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    # Resolved by the service (never None once stored): "list" price.
    price_original: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    discount_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False)
    removed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PriceHistory(Base):
    """Append-only price/availability history (schema.md, CATSVC-R4).

    One entry is written only when the current price OR availability changed
    vs. the last entry. No retention in V1. ``user_id`` is denormalised for
    per-user purges and queries.
    """

    __tablename__ = "price_history"
    __table_args__ = (Index("ix_price_history_product_recorded", "product_id", "recorded_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    price_current: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    price_original: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    discount_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Cart(Base):
    """A user's cart (carts.md, cart-engine.md). Phase 5.

    ``mode`` is **immutable** after creation (CART-R2): no endpoint changes it.
    ``scraper_id`` is the scraper's ``plugin_id`` for ``scraper_specific`` carts and
    NULL for ``cross`` (CART-R4/R5). ``threshold_amount`` is the savings threshold,
    stored as an **absolute € value** (decision 2026-06-29, inverts CART-R9/R10 — the
    percentage is a UI input aid only); NULL = no threshold; the engine fires when the
    final estimate ≤ this amount (CART-R11). Alert types + the per-cart baseline are
    phase 6 (alerts), not here. Per-user (DB-R1)."""

    __tablename__ = "carts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)  # cross | scraper_specific
    scraper_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    threshold_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CartMember(Base):
    """Membership of a catalog product in a cart (CART-R1). Phase 5.

    UNIQUE ``(cart_id, product_id)``; both FKs CASCADE — deleting the cart or the
    product removes the membership (CART-R3/R8, the products cascade realises CAT-R8)."""

    __tablename__ = "cart_members"
    __table_args__ = (UniqueConstraint("cart_id", "product_id", name="uq_cart_members_identity"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cart_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("carts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )


class CartAlertType(Base):
    """An alert type enabled on a cart (schema.md, alerts). Phase 6 (6.B1).

    **Presence of a row = that type is enabled** — there is no ``enabled`` column
    (schema.md). UNIQUE ``(cart_id, alert_type)``; the FK CASCADEs so deleting the cart
    drops its alert types. ``alert_type`` holds an :class:`~src.core.contracts.AlertType`
    value. Enabling the first type seeds the per-cart baseline; clearing them all deletes
    it (6.B2/6.B3)."""

    __tablename__ = "cart_alert_types"
    __table_args__ = (
        UniqueConstraint("cart_id", "alert_type", name="uq_cart_alert_types_identity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cart_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("carts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    alert_type: Mapped[str] = mapped_column(String(48), nullable=False)


class AlertSnapshot(Base):
    """The per-cart alert **baseline** (alert-engine.md, schema.md). Phase 6 (6.B2).

    One row per **(user, cart)** — a composite primary key. ``snapshot_json`` is the
    reference state the next run diffs against: for each (non-delisted) member product
    ``{on_sale, available, price_current}``, plus the cart-level ``all_on_sale`` and
    ``threshold_reached`` flags. Seeded when the first alert type is enabled, advanced on
    every run, deleted when all types are disabled or the cadence goes off (6.B2/6.B3).
    ``taken_at`` records when the baseline was last written."""

    __tablename__ = "alert_snapshot"

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    cart_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("carts.id", ondelete="CASCADE"), primary_key=True
    )
    snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    taken_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AlertLog(Base):
    """One notification in a user's in-app history (schema.md, alerts). Phase 6 (6.B6).

    Written **always**, before any channel delivery (delivery is phase 7). ``kind`` is a
    :class:`~src.core.contracts.NotificationKind` and gives the category; phase 6 writes
    only ``alert_digest``. ``payload_json`` is the full self-sufficient digest (AEV-R2) —
    ``Decimal`` as string, ``datetime`` ISO-8601 (DB-R3). ``read_at`` null = unread (the
    dashboard badge, 6.F4). ``admin_message_id`` stays null until the admin-message table
    arrives in phase 10 (kept as a plain nullable column; the FK lands with that table)."""

    __tablename__ = "alert_log"
    __table_args__ = (Index("ix_alert_log_user_created", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    admin_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AlertDelivery(Base):
    """Per-channel delivery outcome for one notification (notification-architecture.md). Phase 7.

    One row per (notification, channel). ``status`` starts ``pending`` for network channels
    and is set to ``delivered`` / ``failed`` when the worker drains it (the plugin does its own
    short retry/backoff; the drain never re-tries a ``failed`` row — best-effort). The **in-app**
    channel is local, so its row is written already ``delivered`` (or ``skipped`` if the admin has
    disabled it) at digest time, never drained. When the user has no active channel at all, a
    single ``skipped_no_notifier`` row is written with an empty ``plugin_id``. ``error`` carries
    the readable failure reason. The in-app history (``alert_log``) is the source of truth and is
    always written regardless of delivery."""

    __tablename__ = "alert_delivery"
    __table_args__ = (
        Index("ix_alert_delivery_log", "alert_log_id"),
        Index("ix_alert_delivery_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alert_log_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("alert_log.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plugin_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    # pending | delivered | failed | skipped | skipped_no_notifier
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class NotifierAdminConfig(Base):
    """Per-notifier admin config + global toggle (notifier-plugin.md NOT-R2 / PCFG-R8). Phase 7.

    One row per notifier (= plugin_id). ``config_json`` holds the channel-infrastructure fields
    the notifier declares (e.g. SMTP host / credentials, secrets included). ``enabled`` is the
    admin **kill-switch**: ``False`` makes the channel unavailable to everyone (and invisible to
    users), preserving personal configs. In-app has a row too — only ``enabled`` matters (it needs
    no system config). Typed/whitelisted access lives in :mod:`src.core.notifiers`."""

    __tablename__ = "notifier_admin_config"

    plugin_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class NotifierUserConfig(Base):
    """Per-user notifier config + personal activation (profile-and-notifiers.md). Phase 7.

    Composite PK ``(user_id, plugin_id)``. ``config_json`` is the user's personal fields (e.g.
    their delivery address); ``enabled`` is the user's own on/off — disabling keeps the config so
    it can be re-activated without re-typing (PROF-R10). The **in-app** channel is exempt: the user
    cannot disable it, so it never gets a row here (it is always active for the user)."""

    __tablename__ = "notifier_user_config"

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    plugin_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ScrapeCooldown(Base):
    """Anchor for the manual scrape-now cooldown (SCR-R15).

    Holds the **last scrape time per (plugin, user)**, written at the START of any
    scrape — manual now, scheduled from phase 4 — but **read only by the manual
    scrape-now** to enforce the per-scraper minimum interval. Hence the asymmetry:
    a scheduled run starts the manual cooldown (writes), yet is never itself
    rate-limited (never reads). One row per pair, upserted; not a history log
    (run records live in ``scrape_user_log`` from phase 4).
    """

    __tablename__ = "scrape_cooldown"
    __table_args__ = (UniqueConstraint("plugin_id", "user_id", name="uq_scrape_cooldown_identity"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plugin_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    last_scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class FeatureFlag(Base):
    """Dev-only runtime feature flags (4.B1a). ``key`` → JSON ``value`` (the flag's own
    params). Kept in the DB so the web (which sets them via the admin API) and the
    worker (which reads them each tick) — separate processes — share the same values.
    The web clears the table at startup, so flags are **non-persistent**: every boot
    reverts to the code defaults. Admin-only, dev-oriented — not a production toggle.
    """

    __tablename__ = "feature_flags"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class ScraperSchedule(Base):
    """Per-scraper schedule (SCHED-R1, scheduling-models.md): 1..N daily slots, an
    enabled flag, and the last EXECUTED slot. ``times`` are wall-clock ``"HH:MM"`` in the
    installation timezone (sorted, unique); ``last_slot`` is a UTC datetime (not a date)
    so it supports N slots/day and cross-midnight catch-up. One row per scraper (= plugin_id).
    """

    __tablename__ = "scraper_schedule"

    scraper_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    times: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_slot: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ScraperAdminConfig(Base):
    """Per-scraper admin config (PCFG-R2, 4.B10): one row per scraper (= plugin_id),
    ``config_json`` holding the **core reserved keys** (``politeness_delay_ms``,
    ``http_timeout_s``, ``cache_ttl_min``, ``scrape_now_min_interval_s``) the core reads on
    the plugin's behalf (HTTP client, cache, scrape-now cooldown) and, from phase 7+, the
    fields the plugin itself declares (site rules). Typed access via
    :func:`src.core.scraper_config.get_scraper_config`; unknown keys are ignored. No
    ``enabled`` flag — suspension lives in ``scraper_schedule``."""

    __tablename__ = "scraper_admin_config"

    plugin_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class SystemSetting(Base):
    """Global system settings (MNT-R3), key → JSON value, editable at runtime and
    **persistent** (unlike feature_flags). Typed access via
    :func:`src.core.settings.get_system_settings`; 4.B5 reads ``scraper_run_timeout_min``,
    later MVPs grow it (retention, grace period) + the admin editor."""

    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON, nullable=False)


class ScrapeRun(Base):
    """One scraper run — scheduled or manual (scheduling-models.md, 4.B6). Counters are
    aggregated from the per-user deltas + the instrumented HTTP client."""

    __tablename__ = "scrape_run"
    __table_args__ = (Index("ix_scrape_run_scraper_started", "scraper_id", "started_at"),)

    run_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scraper_id: Mapped[str] = mapped_column(String(64), nullable=False)
    trigger: Mapped[str] = mapped_column(String(16), nullable=False)  # "scheduled" | "manual"
    slot: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # running | ok | partial | error | timeout
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    users_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    products_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    products_new: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    price_changes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    products_removed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    products_excluded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    http_requests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cache_hits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(String(512), nullable=True)


class ScrapeUserLog(Base):
    """Per-user detail of a run (one row per user per run, 4.B6). http_requests/cache_hits
    are the share attributed to the user in flight (the run is mono-thread)."""

    __tablename__ = "scrape_user_log"
    __table_args__ = (Index("ix_scrape_user_log_run", "run_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("scrape_run.run_id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    products_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    products_new: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    price_changes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    http_requests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cache_hits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ok")  # ok | error
    error_message: Mapped[str | None] = mapped_column(String(512), nullable=True)


class SystemLog(Base):
    """Operational event log (LOG-R1..R4, 4.B7). The incremental ``id`` doubles as the
    polling cursor (LOG-R3). ``source`` is one of worker | scraper | web | notifier | alert |
    summary; ``level`` info | warning | error. Messages never carry user operational
    content (LOG-R4) — only ids and metrics. Retention by MNT-R2 (worker daily purge)."""

    __tablename__ = "system_log"
    __table_args__ = (Index("ix_system_log_created", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    level: Mapped[str] = mapped_column(String(16), nullable=False)  # info | warning | error
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    message: Mapped[str] = mapped_column(String(2048), nullable=False)
    context_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class ScrapeCache(Base):
    """Scrape response cache (CTX-R9, 4.B8). One row per (plugin_id, cache_key); the key is
    the sha256 of the normalised request (method + URL, sorted query) scoped to the plugin.
    ``expires_at`` enforces the per-plugin half-life: expired rows are ignored on read and
    purged at run start (4.B9). ``response_body`` is the raw bytes; ``response_meta_json``
    keeps status + content-type so a hit reconstructs the response faithfully."""

    __tablename__ = "scrape_cache"
    __table_args__ = (
        UniqueConstraint("plugin_id", "cache_key", name="uq_scrape_cache_identity"),
        Index("ix_scrape_cache_expires", "expires_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plugin_id: Mapped[str] = mapped_column(String(64), nullable=False)
    cache_key: Mapped[str] = mapped_column(String(64), nullable=False)  # sha256 hex
    response_body: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    response_meta_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
