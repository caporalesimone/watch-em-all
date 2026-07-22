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

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.contracts import AlertType
from src.core.models import AlertSnapshot

if TYPE_CHECKING:
    from src.core.cart_engine import CartState
    from src.core.models import CatalogProduct


def snapshot_payload(products: list[CatalogProduct], state: CartState) -> dict[str, Any]:
    """Build the baseline payload for a cart from its member products and computed state.

    Per-product ``{on_sale, available, price_current}`` keyed by the product id (as a
    string, since JSON object keys are strings), plus the cart-level ``all_on_sale`` and
    ``threshold_reached`` flags the cart-event diff compares against. Delisted members are
    excluded (ALERT-R12); a member that appears later is seeded silently by the run that
    meets it. ``Decimal`` is stored as a string (DB-R3)."""
    return {
        "products": {
            str(p.id): {
                "on_sale": (p.discount_pct or 0) > 0,
                "available": p.is_available,
                "price_current": str(p.price_current),
            }
            for p in products
            if not p.removed
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
    products: list[CatalogProduct], snapshot: dict[str, Any], enabled: set[str]
) -> list[ProductDiff]:
    """Diff each current member against the baseline and return the products that earned
    at least one **enabled** tag (alert-engine.md). Rules (ALERT-R9/R11/R12):

    - delisted members are ignored; a member absent from the baseline is skipped (it was
      seeded silently by the run that first met it), so it produces no event;
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
        if m.removed:  # ALERT-R12: delisted products never produce a tag
            continue
        prev = baseline.get(str(m.id))
        if prev is None:  # new in the cart since the baseline → silent, no event
            continue
        prev_price = Decimal(str(prev["price_current"]))
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


def delete_all_snapshots(db: Session, user_id: int) -> int:
    """Drop every baseline of a user (cadence off — ALERT-R3). Returns the number of rows
    removed. Re-enabling the cadence re-seeds from the then-current state, so there is no
    backlog. The caller commits. Wired into the alert-schedule API in 6.B7."""
    count = len(
        db.scalars(select(AlertSnapshot.cart_id).where(AlertSnapshot.user_id == user_id)).all()
    )
    db.execute(sa_delete(AlertSnapshot).where(AlertSnapshot.user_id == user_id))
    return count
