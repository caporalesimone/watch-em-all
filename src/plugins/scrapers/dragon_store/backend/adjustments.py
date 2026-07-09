"""Dragon Store cart adjustments (DRG-R5, 5.B5).

The site's cart rules as a small rules class, applied to a scraper_specific cart's
discounted total. Each rule yields a signed ``Adjustment`` (POSITIVE = saving,
NEGATIVE = cost) carrying the **full i18n key** the frontend localizes (``id``) and
its interpolation ``params``; ``description`` is debug-only. The core sums them.

Phase-5 rule values live here in code (declared); making them admin-editable (the
"discount thresholds" editor) comes with the plugin ConfigFields (phase 7+/9).
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from src.core.contracts import Adjustment

_NS = "dragon_store.adjustments"
_CENT = Decimal("0.01")


class DragonAdjustments:
    """Dragon Store's cart-adjustment rules."""

    # Non-cumulative discount: only the highest band whose minimum is reached applies
    # (min discounted total, percent). Below the first minimum there is no discount.
    discount_bands: tuple[tuple[Decimal, Decimal], ...] = (
        (Decimal("100"), Decimal("5")),
        (Decimal("200"), Decimal("10")),
        (Decimal("300"), Decimal("15")),
    )
    shipping_cost = Decimal("5.00")
    free_shipping_min = Decimal("100")

    def _discount(self, cart_total: Decimal) -> Adjustment | None:
        pct = Decimal("0")
        for minimum, band_pct in self.discount_bands:
            if cart_total >= minimum:
                pct = band_pct
        if pct <= 0:
            return None
        amount = (cart_total * pct / Decimal("100")).quantize(_CENT, rounding=ROUND_HALF_UP)
        return Adjustment(
            id=f"{_NS}.threshold_discount",
            description=f"Threshold discount {pct}%",
            amount=amount,  # positive → a saving
            params={"pct": f"{pct.normalize():f}"},
        )

    def _shipping(self, cart_total: Decimal) -> Adjustment:
        if cart_total >= self.free_shipping_min:
            return Adjustment(
                id=f"{_NS}.free_shipping", description="Free shipping", amount=Decimal("0.00")
            )
        return Adjustment(
            id=f"{_NS}.shipping",
            description="Shipping",
            amount=-self.shipping_cost,  # negative → a cost
            params={"cost": f"{self.shipping_cost:f}"},
        )

    def compute(self, cart_total: Decimal) -> list[Adjustment]:
        out: list[Adjustment] = []
        discount = self._discount(cart_total)
        if discount is not None:
            out.append(discount)
        out.append(self._shipping(cart_total))
        return out


ADJUSTMENTS = DragonAdjustments()
