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
    # Rename and/or set the threshold. The threshold is an absolute € value (5.B4); the
    # percentage is a UI input aid only. `threshold_amount: null` (explicitly present)
    # clears the threshold — the endpoint uses model_fields_set to tell "omitted" from
    # "set to null". mode is never editable (CART-R2).
    name: str | None = Field(default=None, min_length=1, max_length=128)
    threshold_amount: Decimal | None = None


class CartAdjustment(BaseModel):
    # An adjustment line as the cart card shows it (5.B3/5.B5). `id` is the i18n key
    # the FE localizes; `params` feed its interpolation; `description` is debug-only.
    id: str
    description: str
    amount: Decimal
    params: dict[str, str] = Field(default_factory=dict)


class CartMemberOut(BaseModel):
    # A cart member = a catalog product row + whether it counts in the totals (active).
    product_id: int
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
    active: bool


class CartThreshold(BaseModel):
    # Savings-threshold status (5.B4). `amount` is the absolute € target; `current` is
    # the final estimate it compares against; `partial` = reached with excluded members.
    amount: Decimal
    current: Decimal
    reached: bool
    partial: bool


class CartCard(BaseModel):
    # A cart with its computed state (5.B3/5.B4). `members` is only filled in the detail
    # view (CartDetail). `threshold` is null when unset or no active members (CART-R12).
    id: int
    name: str
    mode: str
    scraper_id: str | None
    currency: str | None
    member_count: int
    active_count: int
    excluded_count: int
    has_delisted: bool
    any_on_sale: bool = False
    all_on_sale: bool = False
    total_full: Decimal
    total_discounted: Decimal
    adjustments: list[CartAdjustment] = Field(default_factory=list)
    final_price: Decimal
    threshold_amount: Decimal | None = None  # the stored target (the editor's value)
    threshold: CartThreshold | None = None  # computed status (null without active members)
    alert_types: list[str] = Field(default_factory=list)  # enabled alert types (6.B1)
    created_at: datetime


class CartDetail(CartCard):
    members: list[CartMemberOut] = Field(default_factory=list)


class CartItemsBody(BaseModel):
    # Add/remove cart members by catalog product id (5.B2). The add is validated as
    # a batch: all ids must be the user's, listed (not delisted), of the cart's scraper
    # (scraper_specific) and one currency — else the whole batch is rejected.
    product_ids: list[int] = Field(min_length=1)


class AlertScheduleOut(BaseModel):
    # A user's alert cadence (6.B7). weekdays: 0=Monday … 6=Sunday; [] = off.
    # baseline_effect is set only on a PUT that changed the on/off state (ALERT-R3 UI
    # warning): "cleared" (turned off) or "reseeded" (turned on); null otherwise.
    scheduled_time: str
    weekdays: list[int]
    baseline_effect: str | None = None


class AlertSchedulePut(BaseModel):
    scheduled_time: str = Field(min_length=4, max_length=8)  # "HH:MM" or "HH:MM:SS"
    weekdays: list[int] = Field(default_factory=list)


class CartAlertTypesBody(BaseModel):
    # The full desired set of enabled alert types for a cart (6.B1). Full-set semantics:
    # the endpoint stores exactly this set (presence = enabled). Values are validated
    # against the AlertType enum. Empty list = disable all (deletes the baseline).
    alert_types: list[str] = Field(default_factory=list)
