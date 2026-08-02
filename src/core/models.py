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
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.core.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # The username **is** the email address (10.B23), so the column is sized for one: RFC 5321
    # caps a path at 254 characters, and the old String(64) would have silently refused perfectly
    # ordinary corporate addresses. Stored lower-cased — see `normalise_username`.
    username: Mapped[str] = mapped_column(String(254), unique=True, nullable=False, index=True)
    # Where to write when the username is *not* an address (10.X2). Exactly one account is in
    # that position — the bootstrap admin, because it exists before anybody can type an email —
    # and it is the only one that can set this. For everybody else it stays NULL and the
    # username is the address, so there are never two fields that could disagree about where a
    # person's mail goes.
    contact_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
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
    # When the password currently in place was set (10.X1). Stamped at creation like
    # `created_at` and moved on every password write, so `password_expiry` (10.B19) has an
    # age to measure without a NULL meaning two different things ("never changed" and
    # "predates the column"). It lands one MVP ahead of the logic that reads it: `create_all`
    # does not alter existing tables, so adding it later would be a second database
    # recreation — and that would reset the per-product counters phase 10b is waiting on.
    password_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # Last broadcast this person has read (10.X1, written by 10.B12). A broadcast is one row
    # for everybody rather than a copy per user, so read state cannot live on the message: it
    # lives here, as "read up to N". NULL means no broadcast has ever been read, which is a
    # different statement from 0. Deliberately NOT a foreign key to `admin_message`: that
    # table lands an MVP later and a constraint cannot point at something that does not exist
    # yet, the same reason `price_history` keys by identity instead of by row.
    last_broadcast_read_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
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
    # When the delisting sweep dropped it (9.B6b). `removed` alone cannot say "delisted
    # since when", which the catalog cleanups want to sort on and phase 15 needs to emit
    # its event exactly once. NULL whenever `removed` is false.
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # --- per-product statistics (9.B6b) -------------------------------------------------
    # Counted per catalog row, so per user: two users watching the same product keep their
    # own numbers. Written by the catalog service; how they are shown is phase 10b.
    #
    # Fresh reads only: a delivery served from the scrape cache increments `cache_hits`
    # instead, otherwise this would count "times we re-served a page" rather than times the
    # site actually answered about this product (9.X4, as a counter).
    observations: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Deliveries that came off a cached page. Careful reading it: for a category product a
    # single HTTP cache hit serves up to 50 products, so this means "my data came from a
    # cached page", not "one request saved for me".
    cache_hits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Kept apart on purpose: `scrape_run.price_changes` increments on availability moves and
    # on the first history row too, so it counts "history rows written". These two do not.
    price_changes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    availability_changes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    price_min: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    price_min_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    price_max: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    price_max_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # How long the current price has held — the companion of `last_seen_at`: a flat line
    # reads differently at three days than at eight months.
    last_price_change_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class PluginJob(Base):
    """Progress and cooperative cancellation of one in-flight plugin job (C9/C10).

    It exists to take a **transaction** away from the plugins, not a feature. Progress has to be
    committed while the work is still running — the page polling it cannot see an uncommitted
    row — and the plugin was doing that on the session it had been handed. In a scheduled run
    that session is the *worker's*, mid-``run_for_user``, holding a half-filled
    ``scrape_user_log``: the plugin's commit made that half-row durable, and a process that died
    before the worker finished left it there for ever with a NULL status.

    So the core keeps this book on **its own short-lived session** (the same pattern as the
    scrape cache) and hands the plugin two questions instead of a session: *here is how far I
    have got* and *has anyone asked me to stop?*.

    Keyed ``(plugin_id, job_key)`` — the key is the plugin's own, in its own id space, so the
    core needs to know nothing about what a job is. The row lives as long as the job: it is
    written when work starts and dropped when it reaches a terminal state, so a missing row
    means "nothing of this is running", which is the answer a cancel request needs.
    """

    __tablename__ = "plugin_jobs"
    __table_args__ = (UniqueConstraint("plugin_id", "job_key", name="uq_plugin_jobs_identity"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plugin_id: Mapped[str] = mapped_column(String(64), nullable=False)
    job_key: Mapped[str] = mapped_column(String(64), nullable=False)
    progress_done: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # NULL while the total is not known yet — a category cannot know its size before page one.
    progress_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[str | None] = mapped_column(String(256), nullable=True)
    # Cooperative: the worker reads this at the same checkpoints that write progress. A thread
    # cannot be killed, and does not need to be.
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ProductSource(Base):
    """Which of a user's inputs delivered a catalog product — many-to-many (C14).

    A product is deliberately **not** the child of one watch: the same product can be delivered
    by several categories at once, and that is precisely why a single foreign key was refused
    (9.B4/CATSVC-R2). A many-to-many is the shape that argument asks for, and it answers the
    question a deletion confirmation has to answer — *will this come back?* — with the name of
    the input instead of a conditional.

    The source is **described, not joined**: this is a core table and a watch lives in the
    plugin's own schema (CTX-R6), so there is nothing here to point a FK at. The plugin names
    its own input; the core keeps the description current on every delivery and drops it when
    the plugin says that input is gone.
    """

    __tablename__ = "product_sources"
    __table_args__ = (
        UniqueConstraint("product_id", "source_key", name="uq_product_sources_identity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_key: Mapped[str] = mapped_column(String(64), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    # Refreshed on every delivery: an input the user renamed must not keep its old name here.
    source_label: Mapped[str] = mapped_column(String(512), nullable=False)


class PriceHistory(Base):
    """Append-only price/availability history, **per product and not per user** (schema.md,
    CATSVC-R4).

    A price is a fact about the site, not about a user. Keyed per catalog row this table held
    one chain *per watcher* of the same public fact — duplicated, and free to **diverge**: an
    entry is written against the previous entry of its own chain, so a user who starts watching
    later opens a chain whose "first price" was never the product's first. Keyed on the
    product's identity ``(plugin_id, external_id)`` there is one chain, and one watcher is
    enough to keep it growing for everyone.

    It therefore **outlives** every catalog row that points at it: a user who removes a product
    (or is deleted) leaves the history behind for whoever watches it next, which is knowledge
    the new watcher could not have obtained otherwise. Nothing here is ever pruned — the admin
    gets tools for history no user references any more in a later phase.
    """

    __tablename__ = "price_history"
    __table_args__ = (
        Index("ix_price_history_identity_recorded", "plugin_id", "external_id", "recorded_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Product identity, NOT a foreign key to `products`: that table is per-user, and a
    # cascade from it is exactly what used to destroy the history of a removed product.
    plugin_id: Mapped[str] = mapped_column(String(64), nullable=False)
    external_id: Mapped[str] = mapped_column(String(64), nullable=False)
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


class AdminMessage(Base):
    """One message written by an admin (admin-notifications.md, ADMSG-R1/R6). Phase 10 (10.B12).

    **A broadcast is one row, not one row per user** (Simone's decision, 2026-08-02): what an
    announcement costs stops depending on how many accounts exist, and read state stays private
    because it is never written here at all — each user carries a pointer instead
    (``users.last_broadcast_read_id``). A message to a single user has one recipient already, so
    it takes the ordinary path and lands in that user's ``alert_log``.

    Immutable once sent (ADMSG-R6): there is no edit and no recall, because a message that has
    already reached an inbox cannot be unsent — a mistake is corrected by sending another one.
    ``sender_id`` goes null if the author's account is later deleted; the message stays, since
    the people who received it still have it.
    """

    __tablename__ = "admin_message"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sender_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # "all" = broadcast (the pointer applies) | "user" = one recipient (an alert_log row).
    audience: Mapped[str] = mapped_column(String(8), nullable=False, default="all")
    target_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # Frozen at send time: the audience of an announcement is who it went to *then*, and
    # counting the users table later would answer a different question every month.
    recipient_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AdminMessageDelivery(Base):
    """Per-recipient, per-channel outcome for an admin message (ADMSG-R2/R5). Phase 10 (10.B12).

    A separate table from ``alert_delivery`` for one structural reason: a broadcast has no
    ``alert_log`` row to hang outcomes off, and the outcome is inherently per **user** — the one
    thing ``alert_delivery`` never had to know, because a digest belongs to a single person by
    construction. Same status vocabulary, so the drain logic reads the same either way.

    Note what this table does **not** contain: whether the recipient read it. Delivery is the
    admin's business (ADMSG-R5), reading is not.
    """

    __tablename__ = "admin_message_delivery"
    __table_args__ = (
        Index("ix_admin_msg_delivery_msg", "admin_message_id"),
        Index("ix_admin_msg_delivery_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    admin_message_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("admin_message.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plugin_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    # pending | delivered | failed | skipped | skipped_no_notifier — as alert_delivery.
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


class ProcessStatus(Base):
    """What one of this installation's processes is doing, and when it last said so (PST-R1).

    Named for the question rather than for its first answer. The database is the only thing
    the web and the worker share, so it is the only place either can report on itself to the
    other; a table called ``worker_heartbeat`` would have had to be replaced the first time
    something else needed reporting, and there is no reason to make that mistake on purpose.

    One row per process, **updated in place** — a heartbeat is a state, not an event. Appended
    it would be ~525.000 rows a year at the default tick to answer a question that only ever
    reads the latest one, and those rows would then need a retention policy of their own.

    Kept deliberately small: ``state`` and ``detail`` are here because the worker already has
    something true to put in them (it suspends itself on an incompatible schema, INC-R4) and
    the admin errors feed reads them. A column nothing writes and nobody reads is the mistake
    C7 was about; the room for growth is in the **name and the key**, not in empty columns.
    """

    __tablename__ = "process_status"

    # "worker", "web" — whoever reports. Not an enum: a second worker is a name, not a schema
    # change.
    process: Mapped[str] = mapped_column(String(32), primary_key=True)
    # When this process last said it was alive. The writer rate-limits itself (PST-R2), so this
    # is never more precise than the floor — and does not need to be.
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # What it is doing: "running" | "suspended". Free-form on purpose, same reason as `process`.
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    # Why, when the state calls for it (a suspended worker says what suspended it).
    detail: Mapped[str | None] = mapped_column(String(256), nullable=True)


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


class ScraperStats(Base):
    """Lifetime statistics for one scraper (9.B6c, phase 10 decides how to show them).

    One row per ``plugin_id``, **global** (not per user), and **cumulative**. It exists
    because ``scrape_run`` has retention: aggregating that table answers "recently", never
    "ever". The health group is not a faster query but information nobody records today —
    the 429s, the anti-bot gate and the ``robots.txt`` refusals live only as log lines,
    which is exactly what was missing during the 25 July block, when the question was
    "since when, and how often".

    ``since`` is part of the contract, not decoration: a cumulative counter that never
    resets misleads after a configuration change — politeness went from 1.5s to 11s in
    0.8.1, and totals either side of that are not comparable.
    """

    __tablename__ = "scraper_stats"

    plugin_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    since: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # --- activity ---
    runs_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    runs_ok: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    runs_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    runs_skipped_locked: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Tells "it is failing right now" from "it failed once in March", which is the actual
    # question in front of a monitoring page.
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # --- traffic ---
    http_requests_total: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    cache_hits_total: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    bytes_downloaded_total: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    # Kept apart from total run time on purpose: their ratio says whether the bottleneck is
    # us or the site's Crawl-delay.
    politeness_wait_s_total: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    run_seconds_total: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    # --- health towards the site ---
    rate_limited_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    gate_hits_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    gate_cleared_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    robots_denied_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # --- yield ---
    products_delivered_total: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    pages_fetched_total: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    parse_failures_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class SystemMessageTemplate(Base):
    """An admin's rewrite of one core-generated text (admin-notifications.md, ADMSG-R7..R9).

    **Only overrides live here** (ADMSG-R9). The catalog itself — keys, default texts, declared
    placeholders — is code, in :mod:`src.core.system_messages`, so adding a message to the core
    needs no migration and no seeding: a key with no row *is* its default, and it shows up in the
    admin list the moment it exists. The same reasoning as ``system_settings``, for the same
    reason: a default that has been copied into the database is a default that can go stale.
    """

    __tablename__ = "system_message_template"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
