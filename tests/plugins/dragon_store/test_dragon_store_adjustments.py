"""Unit tests for Dragon Store cart adjustments (5.B5, DRG-R5): non-cumulative
threshold discount bands on the discounted total + shipping (free above €100)."""

from __future__ import annotations

from decimal import Decimal

from src.plugins.scrapers.dragon_store.backend.adjustments import ADJUSTMENTS


def _by_id(total: str) -> dict[str, Decimal]:
    return {a.id: a.amount for a in ADJUSTMENTS.compute(Decimal(total))}


def test_below_first_band_no_discount_paid_shipping() -> None:
    out = ADJUSTMENTS.compute(Decimal("80.00"))
    assert [a.id for a in out] == ["dragon_store.adjustments.shipping"]
    assert out[0].amount == Decimal("-5.00")  # cost (negative)


def test_band_5_percent_and_free_shipping() -> None:
    amounts = _by_id("150.00")
    assert amounts["dragon_store.adjustments.threshold_discount"] == Decimal("7.50")  # 5% of 150
    assert amounts["dragon_store.adjustments.free_shipping"] == Decimal("0.00")


def test_band_10_percent() -> None:
    amounts = _by_id("250.00")
    assert amounts["dragon_store.adjustments.threshold_discount"] == Decimal("25.00")  # 10%


def test_band_15_percent() -> None:
    amounts = _by_id("300.00")
    assert amounts["dragon_store.adjustments.threshold_discount"] == Decimal("45.00")  # 15%


def test_band_is_not_cumulative_and_rounds() -> None:
    out = ADJUSTMENTS.compute(Decimal("199.99"))  # still the 5% band (< 200)
    discount = next(a for a in out if a.id.endswith("threshold_discount"))
    assert discount.params == {"pct": "5"}
    assert discount.amount == Decimal("10.00")  # 199.99 * 5% = 9.9995 -> 10.00
