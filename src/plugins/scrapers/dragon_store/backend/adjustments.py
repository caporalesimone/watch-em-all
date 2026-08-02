"""Dragon Store cart adjustments (DRG-R5, 5.B5).

The site's cart rules as a small rules class, applied to a scraper_specific cart's
discounted total. Each rule yields a signed ``Adjustment`` (POSITIVE = saving,
NEGATIVE = cost) carrying the **full i18n key** the frontend localizes (``id``) and
its interpolation ``params``; ``description`` is debug-only. The core sums them.

**The values are admin-editable since 10.B22.** They were declared here in code from phase 5
with a note saying they would move to config "in phase 7+/9", and they never did — which is
what made 10.F13 a form with nothing to render. Now the numbers arrive from the plugin's
declared config, and the defaults below are only what an installation gets before anybody
touches them.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from src.core.contracts import Adjustment, ConfigField

_NS = "dragon_store.adjustments"
_CENT = Decimal("0.01")

# What the site did in 2026, and what an installation starts from. Three bands, because that
# is what the shop publishes; a fourth would be a schema change, and the shape of the offer
# changing is exactly the kind of thing worth a code change rather than a silent row.
DEFAULT_BANDS: tuple[tuple[str, str], ...] = (("100", "5"), ("200", "10"), ("300", "15"))
DEFAULT_SHIPPING = "5.00"
DEFAULT_FREE_SHIPPING_MIN = "100"


def config_schema() -> list[ConfigField]:
    """The cart rules as fields an admin can change (10.B22).

    One pair of fields per band rather than a single free-form list: a list would need its own
    editor and its own validation, and three pairs of numbers are three pairs of numbers. A
    band whose minimum is left empty is simply not applied, which is how an installation with
    only two tiers says so.
    """
    fields: list[ConfigField] = []
    for index, (minimum, pct) in enumerate(DEFAULT_BANDS, start=1):
        fields.append(
            ConfigField(
                key=f"band{index}_min",
                label_key=f"dragon_store.cfg.band{index}Min",
                type="number",
                default=int(minimum),
            )
        )
        fields.append(
            ConfigField(
                key=f"band{index}_pct",
                label_key=f"dragon_store.cfg.band{index}Pct",
                type="number",
                default=int(pct),
            )
        )
    fields.append(
        ConfigField(
            key="shipping_cost",
            label_key="dragon_store.cfg.shippingCost",
            type="number",
            default=5,
        )
    )
    fields.append(
        ConfigField(
            key="free_shipping_min",
            label_key="dragon_store.cfg.freeShippingMin",
            type="number",
            help_key="dragon_store.cfg.freeShippingMinHelp",
            default=int(DEFAULT_FREE_SHIPPING_MIN),
        )
    )
    return fields


def _decimal(value: Any, fallback: str) -> Decimal:
    """A stored number as a ``Decimal``. Money never goes through ``float`` here: the bands are
    compared against a cart total that is exact, and a 0.1 that is really 0.1000000000000000055
    decides a threshold the wrong way once in a while — which is the worst kind of wrong."""
    if value is None or value == "":
        return Decimal(fallback)
    try:
        return Decimal(str(value))
    except (ArithmeticError, ValueError):
        return Decimal(fallback)


class DragonAdjustments:
    """Dragon Store's cart-adjustment rules, built from the plugin's admin config."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        bands: list[tuple[Decimal, Decimal]] = []
        for index, (minimum, pct) in enumerate(DEFAULT_BANDS, start=1):
            raw_min = cfg.get(f"band{index}_min", minimum)
            if raw_min is None or raw_min == "":
                continue  # a band without a minimum is a band this installation does not have
            bands.append((_decimal(raw_min, minimum), _decimal(cfg.get(f"band{index}_pct"), pct)))
        # Sorted, so a band typed out of order still behaves: the rule is "the highest band
        # whose minimum is reached", and reading them in row order made that depend on how the
        # form happened to be filled in.
        self.discount_bands: tuple[tuple[Decimal, Decimal], ...] = tuple(sorted(bands))
        self.shipping_cost = _decimal(cfg.get("shipping_cost"), DEFAULT_SHIPPING)
        self.free_shipping_min = _decimal(cfg.get("free_shipping_min"), DEFAULT_FREE_SHIPPING_MIN)

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
"""The defaults, for callers with no session to read a config from. The plugin itself keeps a
cached instance built from the stored values (see ``get_adjustments``)."""
