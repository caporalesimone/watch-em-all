"""Pydantic request/response models for the web API (BE-5, BE-19).

JSON is snake_case throughout (api/README). These models make the OpenAPI schema
complete by construction.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field

from src.core.contracts import BrandRef, CategoryRef


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    expires_at: datetime  # expiry of the ACCESS token (AUTH-R)


class ChangePasswordRequest(BaseModel):
    # old_password is required for a normal change; omitted for the forced first
    # change (must_change_password), which appears right after login (auth.md).
    old_password: str | None = None
    new_password: str = Field(min_length=8)  # AUTH-R6


class MeResponse(BaseModel):
    id: int
    username: str
    first_name: str
    last_name: str
    role: str
    locale: str
    must_change_password: bool


class MePatch(BaseModel):
    locale: str | None = None


class HealthResponse(BaseModel):
    status: str
    db: str
    version: str
    # Current server time as ISO8601 with the installation-TZ offset (4.F1): the UI reads it
    # once at render and ticks locally, so timelines use the server clock, not the client's.
    server_time: datetime
    worker_heartbeat_age_s: float | None = None


class UserCreate(BaseModel):
    # Admin-created account (USR-R1/R15): username + first/last name (both required)
    # + role + a temporary password the user must change at first login (USR-R2).
    username: str = Field(min_length=1, max_length=64)
    first_name: str = Field(min_length=1, max_length=64)
    last_name: str = Field(min_length=1, max_length=64)
    role: Literal["admin", "user"]
    temp_password: str = Field(min_length=8)  # AUTH-R6


class AdminUserSummary(BaseModel):
    id: int
    username: str
    first_name: str
    last_name: str
    role: str
    is_active: bool
    must_change_password: bool
    last_login_at: datetime | None
    created_at: datetime


class CatalogItem(BaseModel):
    # One product row of the current user's catalog, as the Product Picker reads
    # it. Money is Decimal (serialised as a JSON string — exact, no float drift).
    id: int
    plugin_id: str
    external_id: str
    url: str
    name: str
    image_url: str | None
    brand: BrandRef | None = None
    tags: list[str] = Field(default_factory=list)
    category: list[CategoryRef] = Field(default_factory=list)
    currency: str
    price_current: Decimal
    price_original: Decimal
    discount_pct: Decimal
    is_available: bool
    removed: bool
    extra: dict[str, Any]
    first_seen_at: datetime
    last_seen_at: datetime


class CatalogPage(BaseModel):
    items: list[CatalogItem]
    total: int
    page: int
    page_size: int


class CartCreate(BaseModel):
    # name + mode (immutable after, CART-R2); scraper_id required for scraper_specific,
    # must be absent/null for cross (validated in the router for a clean error envelope).
    name: str = Field(min_length=1, max_length=128)
    mode: Literal["cross", "scraper_specific"]
    scraper_id: str | None = None


class CartPatch(BaseModel):
    # Phase 5.B1: rename only. The threshold (threshold_pct / threshold_amount with
    # conversion) is added in 5.B4; mode is never editable (CART-R2).
    name: str | None = Field(default=None, min_length=1, max_length=128)


class CartOut(BaseModel):
    # Phase 5.B1 view: cart identity + member count. The computed state (totals,
    # adjustments, threshold) is layered on by the Cart Engine in 5.B3.
    id: int
    name: str
    mode: str
    scraper_id: str | None
    threshold_pct: Decimal | None
    member_count: int
    created_at: datetime


class CartItemsBody(BaseModel):
    # Add/remove cart members by catalog product id (5.B2). The add is validated as
    # a batch: all ids must be the user's, listed (not delisted), of the cart's scraper
    # (scraper_specific) and one currency — else the whole batch is rejected.
    product_ids: list[int] = Field(min_length=1)
