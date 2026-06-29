"""Cart Engine (cart-engine.md). Phase 5.

A pure read of a cart's current economic state from the catalog: which members are
active vs excluded, the full / discounted totals over the **active** members, the
plugin's adjustments (scraper_specific only) and the resulting final estimate. It
persists nothing — the API, alert engine and summary call it on demand.

5.B3 computes totals + the ``has_delisted`` health flag. The threshold state is
layered on in 5.B4. Adjustments are supplied by the caller as a bound callable
(the web layer resolves the plugin from ``app.state``), so the core never imports
the web (same pattern as ``update_catalog`` taking its session).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.contracts import Adjustment
    from src.core.models import CatalogProduct

# A bound plugin.get_adjustments: (active products, discounted total) -> adjustments.
# String forward refs so the alias builds at runtime without importing those names.
AdjustmentFn = Callable[[list["CatalogProduct"], Decimal], list["Adjustment"]]


@dataclass
class CartState:
    """The computed state of one cart (5.B3). Money fields are ``Decimal``."""

    currency: str | None  # the cart's single currency (None if empty)
    total_full: Decimal  # Σ price_original of active members
    total_discounted: Decimal  # Σ price_current of active members
    adjustments: list[Adjustment]  # scraper_specific only; [] otherwise
    final_price: Decimal  # total_discounted − Σ adjustment.amount
    active_count: int
    excluded_count: int
    has_delisted: bool  # any member delisted → the cart is "unhealthy"


def _is_active(p: CatalogProduct) -> bool:
    """Active = available and not delisted (cart-engine.md). Only active members
    enter the totals (CART-R8)."""
    return p.is_available and not p.removed


def evaluate_cart(
    mode: str,
    products: list[CatalogProduct],
    get_adjustments: AdjustmentFn | None = None,
) -> CartState:
    """Compute a cart's state from its member products. ``get_adjustments`` is bound
    to the cart's scraper by the caller and only consulted for ``scraper_specific``
    carts with at least one active member (CART-R7)."""
    active = [p for p in products if _is_active(p)]

    total_full = sum((p.price_original for p in active), Decimal(0))
    total_discounted = sum((p.price_current for p in active), Decimal(0))

    adjustments: list[Adjustment] = []
    if mode == "scraper_specific" and active and get_adjustments is not None:
        adjustments = get_adjustments(active, total_discounted)
    final_price = total_discounted - sum((a.amount for a in adjustments), Decimal(0))

    currency = active[0].currency if active else (products[0].currency if products else None)

    return CartState(
        currency=currency,
        total_full=total_full,
        total_discounted=total_discounted,
        adjustments=adjustments,
        final_price=final_price,
        active_count=len(active),
        excluded_count=len(products) - len(active),
        has_delisted=any(p.removed for p in products),
    )
