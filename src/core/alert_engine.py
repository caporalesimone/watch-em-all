"""Alert Engine (alert-engine.md). Phase 6.

The notification engine: at the user's alert time it diffs every cart with active
alert types against its **baseline**, aggregates the events into a single digest, writes
it to the in-app history and advances the baseline. This module grows across the phase:

- 6.B2/6.B3 — the **baseline** (``alert_snapshot``): seed, load, advance, delete.
- 6.B4/6.B5 — the **diff** (product tags + cart events) against the baseline.
- 6.B6      — the aggregated ``AlertEvent`` written to ``alert_log``.

Delivery to external channels is phase 7; here the digest only lands in the history.
"""

from __future__ import annotations

from collections.abc import Callable, Container
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel
from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.cart_engine import AdjustmentFn, evaluate_cart
from src.core.contracts import AlertType, NotificationKind
from src.core.models import (
    AlertLog,
    AlertSnapshot,
    Cart,
    CartAlertType,
    CartMember,
    CatalogProduct,
)

if TYPE_CHECKING:
    from src.core.cart_engine import CartState

# Resolves the bound ``get_adjustments`` for a scraper_specific cart (or None). Supplied by
# the caller (worker/web) so the engine never imports the plugins — same pattern as the
# carts API. Cross carts and unloaded scrapers get None.
AdjusterProvider = Callable[[Cart], "AdjustmentFn | None"]


def snapshot_payload(products: list[CatalogProduct], state: CartState) -> dict[str, Any]:
    """Build the baseline payload for a cart from its member products and computed state.

    Per-product ``{on_sale, available, price_current, removed}`` keyed by the product id (as
    a string, since JSON object keys are strings), plus the cart-level ``all_on_sale`` and
    ``threshold_reached`` flags the cart-event diff compares against. A member that appears
    later is seeded silently by the run that meets it. ``Decimal`` is stored as a string
    (DB-R3).

    Delisted members are **in** the baseline since 9.B9: excluding them made delisting
    invisible — the row vanished from the reference state, so the transition into it had
    nothing to be a transition from. ``removed`` is what makes ``PRODUCT_DELISTED`` fire once
    (ALERT-R12) instead of every run."""
    return {
        "products": {
            str(p.id): {
                "on_sale": (p.discount_pct or 0) > 0,
                "available": p.is_available,
                "price_current": str(p.price_current),
                "removed": p.removed,
            }
            for p in products
        },
        "all_on_sale": state.all_on_sale,
        "threshold_reached": bool(state.threshold and state.threshold.reached),
    }


@dataclass
class ProductDiff:
    """One product's alert result for a run (6.B4): the tags it earned versus the
    baseline, with the previous/current price for the digest. ``product`` is the current
    catalog row (the digest reads its name/url/plugin_id/discount/currency from it)."""

    product: CatalogProduct
    tags: list[AlertType]
    price_previous: Decimal
    price_current: Decimal


def diff_products(
    products: list[CatalogProduct], snapshot: dict[str, Any], enabled: Container[str]
) -> list[ProductDiff]:
    """Diff each current member against the baseline and return the products that earned
    at least one **enabled** tag (alert-engine.md). Rules (ALERT-R9/R11/R12):

    - a member absent from the baseline is skipped (it was seeded silently by the run that
      first met it), so it produces no event;
    - ``PRODUCT_DELISTED`` fires on the transition into delisting and **only** there; a
      product that is already delisted produces nothing at all, price included — its row
      keeps the last price the site showed, and that number stops being news the moment the
      product stops being for sale (ALERT-R12);
    - ``PRODUCT_ON_SALE`` fires when a product enters a discount **or** drops further while
      already on sale (a price change in the buyer's favour);
    - ``PRODUCT_OFF_SALE`` when it leaves the discount; availability transitions give
      ``PRODUCT_UNAVAILABLE`` / ``PRODUCT_AVAILABLE_AGAIN``.

    ``PRODUCT_ALL_TIME_LOW`` is not evaluated here — it depends on price analytics (phase
    11, 11.B5). Tags are filtered to ``enabled`` (ALERT-R5); a product with none is dropped.
    """
    baseline: dict[str, Any] = snapshot.get("products", {})
    out: list[ProductDiff] = []
    for m in products:
        prev = baseline.get(str(m.id))
        if prev is None:  # new in the cart since the baseline → silent, no event
            continue
        prev_price = Decimal(str(prev["price_current"]))
        was_removed = bool(prev.get("removed", False))
        if m.removed:
            if was_removed:  # already delisted: no event of any kind (ALERT-R12)
                continue
            if AlertType.PRODUCT_DELISTED in enabled:
                out.append(
                    ProductDiff(
                        product=m,
                        tags=[AlertType.PRODUCT_DELISTED],
                        price_previous=prev_price,
                        price_current=m.price_current,
                    )
                )
            continue
        if was_removed:
            # Back in the delivery. Its baseline describes the product as it was before it
            # vanished, so diffing against it would report a price move nobody made; the run
            # that meets it again re-seeds silently, like a member met for the first time.
            # The re-listing event itself is phase 15 (catalog notifications).
            continue
        now_sale = (m.discount_pct or 0) > 0
        tags: list[AlertType] = []
        if now_sale and (not prev["on_sale"] or m.price_current < prev_price):
            tags.append(AlertType.PRODUCT_ON_SALE)  # entered sale or dropped further (ALERT-R11)
        if prev["on_sale"] and not now_sale:
            tags.append(AlertType.PRODUCT_OFF_SALE)
        if prev["available"] and not m.is_available:
            tags.append(AlertType.PRODUCT_UNAVAILABLE)
        if not prev["available"] and m.is_available:
            tags.append(AlertType.PRODUCT_AVAILABLE_AGAIN)
        tags = [t for t in tags if t in enabled]
        if tags:
            out.append(
                ProductDiff(
                    product=m, tags=tags, price_previous=prev_price, price_current=m.price_current
                )
            )
    return out


def diff_cart_events(
    state: CartState, snapshot: dict[str, Any], enabled: Container[str]
) -> list[AlertType]:
    """Diff the cart-level events against the baseline (alert-engine.md, ALERT-R10):

    - ``CART_ALL_ON_SALE`` when every active member becomes discounted (a false→true
      transition of ``all_on_sale``);
    - ``CART_THRESHOLD_REACHED`` / ``CART_THRESHOLD_REACHED_PARTIAL`` when the threshold
      becomes reached (false→true); the *partial* variant is chosen when some members are
      excluded from the totals.

    A cart with no active members has ``all_on_sale = False`` and ``threshold = None``
    (CART-R12), so both are naturally guarded. Events are filtered to ``enabled`` (ALERT-R5)."""
    events: list[AlertType] = []
    if (
        AlertType.CART_ALL_ON_SALE in enabled
        and state.all_on_sale
        and not snapshot.get("all_on_sale", False)
    ):
        events.append(AlertType.CART_ALL_ON_SALE)
    if state.threshold and state.threshold.reached and not snapshot.get("threshold_reached", False):
        ev = (
            AlertType.CART_THRESHOLD_REACHED_PARTIAL
            if state.threshold.partial
            else AlertType.CART_THRESHOLD_REACHED
        )
        if ev in enabled:
            events.append(ev)
    return events


def get_snapshot(db: Session, user_id: int, cart_id: int) -> AlertSnapshot | None:
    """The cart's baseline row, or ``None`` if it was never seeded."""
    return db.get(AlertSnapshot, (user_id, cart_id))


def upsert_snapshot(
    db: Session, user_id: int, cart_id: int, payload: dict[str, Any]
) -> AlertSnapshot:
    """Seed or advance the baseline: write ``payload`` as the cart's reference state.
    Used both for the initial silent seed (6.B2) and for the per-run advance (6.B4+).
    The caller commits."""
    row = db.get(AlertSnapshot, (user_id, cart_id))
    if row is None:
        row = AlertSnapshot(user_id=user_id, cart_id=cart_id, snapshot_json=payload)
        db.add(row)
    else:
        row.snapshot_json = payload
    return row


def delete_snapshot(db: Session, user_id: int, cart_id: int) -> None:
    """Drop the cart's baseline (all types disabled, or cadence off). The caller commits."""
    db.execute(
        sa_delete(AlertSnapshot).where(
            AlertSnapshot.user_id == user_id, AlertSnapshot.cart_id == cart_id
        )
    )


# ---------------------------------------------------------------------------
# Digest payload (alert-event.md) — the self-sufficient AlertEvent written to the
# history and (from phase 7) handed to the notifiers. Decimal serialises to a string
# and datetime to ISO-8601 via model_dump(mode="json") (DB-R3 / AEV-R4).
# ---------------------------------------------------------------------------


class ThresholdInfo(BaseModel):
    target: Decimal  # the € threshold (fixed amount; CART-R9)
    current: Decimal  # current final estimate
    reached: bool
    partial: bool  # reached while some members are excluded
    excluded: list[str] = []  # names of the excluded products (the PARTIAL case)


class CartTotals(BaseModel):
    full: Decimal
    discounted: Decimal
    final: Decimal


def price_difference(
    previous: Decimal | None, current: Decimal, *, delisted: bool = False
) -> str | None:
    """The signed percentage change from *Was* to *Now* — the digest's **Difference** column
    (9.X10), rendered once here so the email and the in-app history cannot disagree (C19).

    ``None`` means "there is nothing to report", which both renderers show as an em dash. Two
    cases produce it. Without a previous price there is nothing to compare against. And a
    **delisted** product has ``price_previous == price_current`` by construction — nothing moved,
    the product left the site — so a percentage there prints ``0%`` on a row nobody can buy,
    which reads as "the price held" instead of "this is gone".

    Deliberately **not** the product's sale discount: that compares against the list price, a
    different quantity, and printing it under a `Was → Now` pair produced `-0%` on a product
    whose price had just gone *up*. One decimal, dropped when it is zero, so a real but sub-1%
    change never collapses into a misleading ``0%``.
    """
    if delisted or previous is None or previous == 0:
        return None
    pct = (current - previous) / previous * Decimal(100)
    rounded = pct.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    if rounded == 0:  # also catches -0.0, which would otherwise print as "-0%"
        return "0%"
    whole = rounded.to_integral_value()
    text = f"{whole:.0f}" if rounded == whole else f"{rounded:.1f}"
    return f"+{text}%" if rounded > 0 else f"{text}%"


class ProductAlertPayload(BaseModel):
    product_id: int
    name: str
    url: str
    plugin_id: str  # PROVENANCE: always present (cross carts!)
    tags: list[AlertType]
    price_previous: Decimal | None
    price_current: Decimal
    discount_pct: Decimal
    currency: str = "EUR"
    # The Difference column, already rendered (C19). It travels in the payload because the rule
    # existed twice — Python for the email, TypeScript for the page — and 9.F8 declared that
    # debt rather than paying it: the payload is stored, so digests already written would not
    # have carried the field. The 0.9.0 schema reset removes that obstacle.
    difference: str | None = None


class CartAlertPayload(BaseModel):
    cart_id: int
    cart_name: str
    mode: str  # "cross" | "scraper_specific"
    cart_events: list[AlertType] = []
    products: list[ProductAlertPayload] = []
    totals: CartTotals
    threshold: ThresholdInfo | None = None


class AlertEvent(BaseModel):
    kind: NotificationKind = NotificationKind.ALERT_DIGEST
    user_id: int
    generated_at: datetime
    cart_alerts: list[CartAlertPayload]  # only carts with at least one event (AEV-R1)


def _is_active(p: CatalogProduct) -> bool:
    return p.is_available and not p.removed


def _carts_with_alert_types(db: Session, user_id: int) -> list[Cart]:
    """The user's carts that have at least one alert type enabled (only these are run)."""
    return list(
        db.scalars(
            select(Cart)
            .join(CartAlertType, CartAlertType.cart_id == Cart.id)
            .where(Cart.user_id == user_id)
            .distinct()
            .order_by(Cart.id.asc())
        ).all()
    )


def _enabled_types(db: Session, cart_id: int) -> set[str]:
    return set(
        db.scalars(select(CartAlertType.alert_type).where(CartAlertType.cart_id == cart_id)).all()
    )


def _member_products(db: Session, cart_id: int) -> list[CatalogProduct]:
    return list(
        db.scalars(
            select(CatalogProduct)
            .join(CartMember, CartMember.product_id == CatalogProduct.id)
            .where(CartMember.cart_id == cart_id)
        ).all()
    )


def _build_cart_alert(
    cart: Cart,
    state: CartState,
    products: list[CatalogProduct],
    pdiffs: list[ProductDiff],
    cevents: list[AlertType],
) -> CartAlertPayload:
    """Assemble one cart's contribution to the digest — its product tags (with prices and
    provenance) and cart events, plus totals and threshold state (AEV-R2)."""
    product_payloads = [
        ProductAlertPayload(
            product_id=d.product.id,
            name=d.product.name,
            url=d.product.url,
            plugin_id=d.product.plugin_id,
            tags=d.tags,
            price_previous=d.price_previous,
            price_current=d.price_current,
            discount_pct=d.product.discount_pct or Decimal(0),
            currency=d.product.currency,
            difference=price_difference(
                d.price_previous,
                d.price_current,
                # A delisted product's two prices are equal by construction, so a percentage
                # would print 0% on a row nobody can buy. The tag is already in the payload
                # and comes out on its own (9.B9), so nothing new has to be inferred.
                delisted=AlertType.PRODUCT_DELISTED in d.tags,
            ),
        )
        for d in pdiffs
    ]
    threshold = None
    if state.threshold is not None:
        excluded = [p.name for p in products if not _is_active(p)]
        threshold = ThresholdInfo(
            target=state.threshold.amount,
            current=state.threshold.current,
            reached=state.threshold.reached,
            partial=state.threshold.partial,
            excluded=excluded,
        )
    return CartAlertPayload(
        cart_id=cart.id,
        cart_name=cart.name,
        mode=cart.mode,
        cart_events=cevents,
        products=product_payloads,
        totals=CartTotals(
            full=state.total_full, discounted=state.total_discounted, final=state.final_price
        ),
        threshold=threshold,
    )


def run_for_user(
    db: Session,
    user_id: int,
    adjuster_provider: AdjusterProvider,
    now: datetime | None = None,
) -> AlertLog | None:
    """Run the alert engine for one user (6.B6): diff every cart with active alert types
    against its baseline, aggregate the events into a single ``AlertEvent`` per user, write
    it to ``alert_log`` (always, before any delivery) and advance every baseline. Returns
    the written log row, or ``None`` when nothing changed. Delivery to channels is phase 7.

    ``adjuster_provider`` binds each scraper_specific cart's ``get_adjustments`` so the core
    never imports the plugins. The caller commits nothing extra — this function commits."""
    when = now or datetime.now(UTC)
    digest: list[CartAlertPayload] = []
    for cart in _carts_with_alert_types(db, user_id):
        enabled = _enabled_types(db, cart.id)
        products = _member_products(db, cart.id)
        state = evaluate_cart(cart.mode, products, adjuster_provider(cart), cart.threshold_amount)

        snap = get_snapshot(db, user_id, cart.id)
        if snap is None:  # safety net: never seeded → seed silently, no event this run
            upsert_snapshot(db, user_id, cart.id, snapshot_payload(products, state))
            continue

        pdiffs = diff_products(products, snap.snapshot_json, enabled)
        cevents = diff_cart_events(state, snap.snapshot_json, enabled)
        if pdiffs or cevents:
            digest.append(_build_cart_alert(cart, state, products, pdiffs, cevents))
        upsert_snapshot(db, user_id, cart.id, snapshot_payload(products, state))  # advance ALWAYS

    if not digest:
        db.commit()  # baselines advanced even with nothing to notify
        return None

    event = AlertEvent(user_id=user_id, generated_at=when, cart_alerts=digest)
    log = AlertLog(
        user_id=user_id,
        kind=NotificationKind.ALERT_DIGEST.value,
        payload_json=event.model_dump(mode="json"),
        created_at=when,
    )
    db.add(log)  # written ALWAYS, before any channel delivery (phase 7)
    db.commit()
    return log
