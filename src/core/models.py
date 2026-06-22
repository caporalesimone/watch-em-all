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
    product_properties: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
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
