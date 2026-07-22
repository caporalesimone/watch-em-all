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

from typing import TYPE_CHECKING, Any

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.orm import Session

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
