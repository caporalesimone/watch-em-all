"""Pydantic request/response models for the web API (BE-5, BE-19).

JSON is snake_case throughout (api/README). These models make the OpenAPI schema
complete by construction.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field

from src.core.contracts import BrandRef, CategoryRef, ConfigField
from src.core.price_history import Range


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
    # Three levels since 9.B8. A role is chosen at creation and not changed afterwards:
    # promoting an existing account is phase 10, where the actions on accounts live.
    role: Literal["admin", "super_user", "user"]
    temp_password: str = Field(min_length=8)  # AUTH-R6


class RunSummary(BaseModel):
    """One scrape run as the monitoring list shows it (10.B6)."""

    run_id: int
    scraper_id: str
    trigger: str
    slot: datetime | None
    started_at: datetime
    finished_at: datetime | None
    status: str
    users_processed: int
    products_found: int
    products_new: int
    price_changes: int
    products_removed: int
    products_excluded: int
    http_requests: int
    cache_hits: int
    error_message: str | None


class RunUserDetail(BaseModel):
    """One user's share of a run (10.B6). `username` is resolved here rather than left as an
    id: the whole point of the drill-down is to answer *who* failed, and an id does not."""

    user_id: int
    username: str | None
    started_at: datetime
    finished_at: datetime | None
    status: str
    products_found: int
    products_new: int
    price_changes: int
    http_requests: int
    cache_hits: int
    error_message: str | None


class RunPage(BaseModel):
    items: list[RunSummary]
    total: int


class DashboardTotals(BaseModel):
    """System-wide counts for the admin dashboard (10.B9). Aggregates only, never content
    (DASH-R6): the admin governs the installation, they do not read anybody's carts."""

    users_total: int
    users_active: int
    users_deleting: int
    products_total: int
    products_delisted: int
    carts_total: int
    price_history_rows: int
    watched_scrapers: int


class DashboardNotifications(BaseModel):
    """Delivery health over a window (10.B9): how much went out, and how much failed."""

    window_days: int
    alerts: int
    delivered: int
    failed: int
    skipped: int


class DashboardResponse(BaseModel):
    totals: DashboardTotals
    notifications: DashboardNotifications


class UserLoadRow(BaseModel):
    """What one account costs the installation (10.B10). Numbers and a username, nothing
    else: DASH-R6 lets the admin see the load a person creates, never what they are watching."""

    user_id: int
    username: str | None
    scraper_id: str | None = None
    products: int
    carts: int
    http_requests: int
    cache_hits: int


class DashboardUsers(BaseModel):
    window_days: int
    by_user: list[UserLoadRow]
    by_user_and_scraper: list[UserLoadRow]


class CalendarSlot(BaseModel):
    """One planned run on a given day (10.B18, SCHED-R10).

    ``avg_seconds`` is what recent runs of this scraper actually took, so the calendar can
    draw a block with a width instead of a tick — null when there is nothing to average, and
    null is honest: an invented default would draw a confident block around a guess.
    """

    scraper_id: str
    at: datetime
    enabled: bool
    avg_seconds: int | None


class CalendarDay(BaseModel):
    date: str
    slots: list[CalendarSlot]


class AdminPasswordReset(BaseModel):
    # Same shape as creation (10.B1): the admin supplies the temporary password rather than
    # the server inventing one, so the single generator already in the admin page keeps
    # being the only place that decides what a temporary password looks like.
    temp_password: str = Field(min_length=8)  # AUTH-R6


class AdminUserPatch(BaseModel):
    # Enable / disable (10.B1). Only the flag: the role is chosen at creation and not
    # changed afterwards, and the name is the person's, not the administrator's to edit.
    is_active: bool


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
    # Deferred deletion (10.B3). Both null on a normal account; together they are the
    # "being deleted" state the status filter reads and the page shows as a countdown.
    deletion_marked_at: datetime | None = None
    deletion_due_at: datetime | None = None


class CatalogItemSource(BaseModel):
    """One input that delivers a catalog product (C14): its kind, and a name to show.

    No key: the page needs to *say* where a product comes from, not act on it, and shipping the
    plugin's internal id would invite a client to build a link on something it does not own.
    """

    kind: str
    label: str


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
    # Which of the user's inputs still deliver this product (C14). Empty means nothing does, so
    # deleting it is final; non-empty is what lets the confirmation name what will bring it back
    # instead of hedging. Plural because two categories can deliver the same product.
    sources: list[CatalogItemSource] = Field(default_factory=list)
    # How many of the user's carts hold it. Deleting a product removes it from all of them
    # (CART-R8) and the cascade is silent, so the confirmation has to be able to count it.
    in_carts: int = 0


class DelistedSummary(BaseModel):
    """What "remove the delisted products" is about to do, before it does it (C7).

    ``total`` is every delisted row, not the ones visible on the current page — the button
    removes them all, so a count taken from twenty visible rows would understate the click.
    ``in_carts`` is how many of those are in at least one cart, which is the part the user
    cannot see from the catalog table at all.
    """

    total: int
    in_carts: int


class CatalogPage(BaseModel):
    items: list[CatalogItem]
    total: int
    page: int
    page_size: int


class PricePoint(BaseModel):
    # One point of a price series (phase 8): discounted price + availability at a timestamp.
    # Money is Decimal (serialised as a JSON string — exact). A step line is drawn client-side;
    # `available=false` marks where the line must break (no interpolation, HIST-R2).
    t: datetime
    price: Decimal
    available: bool


class ProductHistory(BaseModel):
    # The stepped price series for one product over the requested range (phase 8, 8.B1).
    product_id: int
    range: Range
    points: list[PricePoint] = Field(default_factory=list)


class CartPricePoint(BaseModel):
    # One point of a cart series: the summed total of the available members at a timestamp.
    t: datetime
    total: Decimal


class CartHistory(BaseModel):
    # The stepped total series for one cart over the requested range (phase 8, 8.B2).
    cart_id: int
    range: Range
    points: list[CartPricePoint] = Field(default_factory=list)


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


class AlertListItem(BaseModel):
    # A row of the alert history list (6.B8). `read` = read_at is set; `cart_count` is the
    # number of carts in a digest (0 for non-digest kinds) — a light preview for the list.
    # `source` says which table the id belongs to (10.B12): the history is a union of the
    # user's own rows and the shared announcements, and the two id spaces are independent.
    id: int
    source: str = "alert"  # alert | broadcast
    kind: str
    created_at: datetime
    read: bool
    cart_count: int
    # The message title, for the text kinds only (10.F10). A digest has no title — its one-line
    # preview is the cart count — so this is null there rather than a manufactured heading.
    title: str | None = None


class AlertPage(BaseModel):
    items: list[AlertListItem]
    total: int
    page: int
    page_size: int


class AlertDeliveryOut(BaseModel):
    # One per-channel delivery outcome of a notification (7.F5). `plugin_id` is empty for the
    # `skipped_no_notifier` marker. `error` carries the readable failure reason on `failed`.
    plugin_id: str
    status: str  # pending | delivered | failed | skipped | skipped_no_notifier
    error: str | None = None
    updated_at: datetime


class AlertDetail(BaseModel):
    # One notification in full (6.B8): the self-sufficient digest payload plus its read state
    # and the per-channel delivery outcomes (7.F5).
    id: int
    source: str = "alert"  # alert | broadcast — see AlertListItem
    kind: str
    created_at: datetime
    read: bool
    payload: dict[str, Any]
    deliveries: list[AlertDeliveryOut] = Field(default_factory=list)


# --------------------------------------------------------------- admin messages (phase 10.B12)


class AdminMessageCreate(BaseModel):
    # What the admin composes (ADMSG-R1). `target_user_id` absent = every active account.
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=20_000)  # Markdown (AEV-R7)
    target_user_id: int | None = None


class AdminMessageOut(BaseModel):
    # A sent message as the admin sees it. `recipient_count` is frozen at send time, so it keeps
    # saying who it went to even after accounts come and go.
    id: int
    audience: str  # all | user
    target_user_id: int | None
    target_username: str | None
    title: str
    body: str
    recipient_count: int
    created_at: datetime


class MessageOutcomeCounts(BaseModel):
    # How the send went, per status (10.B13). Deliberately not "read": ADMSG-R5 gives the admin
    # delivery, not reception — whether somebody opened it is theirs.
    delivered: int = 0
    pending: int = 0
    failed: int = 0
    skipped: int = 0  # includes `skipped_no_notifier`: in-app only, which is still a delivery


class AdminMessageSummary(AdminMessageOut):
    sender_username: str | None
    outcomes: MessageOutcomeCounts


class AdminMessagePage(BaseModel):
    items: list[AdminMessageSummary]
    total: int
    page: int
    page_size: int


class MessageRecipientOut(BaseModel):
    # One recipient of a message and how each of their channels went.
    user_id: int
    username: str
    channels: list[AlertDeliveryOut] = Field(default_factory=list)


class AdminMessageDetail(AdminMessageSummary):
    recipients: list[MessageRecipientOut] = Field(default_factory=list)


# --------------------------------------------------------------------------- notifiers (phase 7)


class NotifierChannelOut(BaseModel):
    # A notifier channel as the user's Profile sees it (GET /api/notifiers, PROF-R6/R7).
    # `config` holds only the non-secret stored values; `is_set` flags whether each secret has
    # a stored value (CFG-R3, never the value). In-app: no user schema, always active.
    plugin_id: str
    display_name: str
    is_in_app: bool
    user_schema: list[ConfigField] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)
    is_set: dict[str, bool] = Field(default_factory=dict)
    available: bool  # admin config complete (channel usable)
    user_config_complete: bool
    enabled: bool  # the user's own on/off (always True for in-app)
    active: bool  # delivers to this user


class AdminNotifierOut(BaseModel):
    # A notifier channel as the admin's page sees it (GET /api/admin/notifiers). `user_schema`
    # is included so the admin can supply a minimal target for the channel test (POST .../test).
    plugin_id: str
    display_name: str
    is_in_app: bool
    admin_schema: list[ConfigField] = Field(default_factory=list)
    user_schema: list[ConfigField] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)
    is_set: dict[str, bool] = Field(default_factory=dict)
    enabled: bool  # the admin kill-switch (PCFG-R8)
    admin_config_complete: bool


class NotifierConfigBody(BaseModel):
    # Save a channel's config (user or admin). Keys are filtered on the relevant schema; an
    # omitted secret key keeps the stored value (CFG-R3/R5).
    config: dict[str, Any] = Field(default_factory=dict)


class NotifierEnabledBody(BaseModel):
    enabled: bool


class NotifierTestBody(BaseModel):
    # Ad-hoc user fields for a test send (e.g. a target address). Empty for a user's own test
    # (their stored config is used); the admin supplies the minimal user fields to probe a channel.
    config: dict[str, Any] = Field(default_factory=dict)


class NotifierTestResult(BaseModel):
    ok: bool
    error: str | None = None


class UnreadCount(BaseModel):
    count: int


class AlertIdsBody(BaseModel):
    # Bulk delete of the user's own alerts (6.F3). Ids not owned by the caller are ignored.
    ids: list[int] = Field(min_length=1)


class CartAlertTypesBody(BaseModel):
    # The full desired set of enabled alert types for a cart (6.B1). Full-set semantics:
    # the endpoint stores exactly this set (presence = enabled). Values are validated
    # against the AlertType enum. Empty list = disable all (deletes the baseline).
    alert_types: list[str] = Field(default_factory=list)


class RemovedCount(BaseModel):
    """How many catalog rows a cleanup removed (9.B7). A count, not a bare 204: "nothing was
    delisted" and "twelve products went" are different answers to the same click."""

    removed: int
