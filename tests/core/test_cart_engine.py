"""Unit tests for the Cart Engine (5.B3): active/excluded split, totals over active
members, adjustments for scraper_specific carts, and the has_delisted health flag."""

from __future__ import annotations

from decimal import Decimal

from src.core.cart_engine import evaluate_cart
from src.core.contracts import Adjustment
from src.core.models import CatalogProduct


def _p(
    current: str,
    original: str,
    *,
    available: bool = True,
    removed: bool = False,
    currency: str = "EUR",
) -> CatalogProduct:
    return CatalogProduct(
        price_current=Decimal(current),
        price_original=Decimal(original),
        is_available=available,
        removed=removed,
        currency=currency,
    )


def test_empty_cart() -> None:
    s = evaluate_cart("cross", [])
    assert s.total_full == Decimal(0)
    assert s.total_discounted == Decimal(0)
    assert s.final_price == Decimal(0)
    assert s.currency is None
    assert (s.active_count, s.excluded_count) == (0, 0)
    assert s.has_delisted is False
    assert s.adjustments == []


def test_only_active_members_count_and_delisted_flag() -> None:
    products = [
        _p("10.00", "12.00"),  # active
        _p("5.00", "5.00", available=False),  # out of stock → excluded
        _p("8.00", "8.00", removed=True),  # delisted → excluded + unhealthy
    ]
    s = evaluate_cart("cross", products)
    assert s.total_full == Decimal("12.00")
    assert s.total_discounted == Decimal("10.00")
    assert s.final_price == Decimal("10.00")  # cross → no adjustments
    assert (s.active_count, s.excluded_count) == (1, 2)
    assert s.has_delisted is True


def test_scraper_specific_applies_signed_adjustments() -> None:
    def adj(products: list[CatalogProduct], total: Decimal) -> list[Adjustment]:
        assert total == Decimal("30.00")
        return [
            Adjustment(id="disc", description="discount", amount=Decimal("3.00")),  # saving
            Adjustment(id="ship", description="shipping", amount=Decimal("-5.00")),  # cost
        ]

    products = [_p("10.00", "10.00"), _p("20.00", "25.00")]
    s = evaluate_cart("scraper_specific", products, adj)
    assert s.total_discounted == Decimal("30.00")
    assert s.total_full == Decimal("35.00")
    # final = discounted − Σ amount = 30 − (3 − 5) = 32
    assert s.final_price == Decimal("32.00")
    assert len(s.adjustments) == 2


def test_no_adjustments_without_active_members() -> None:
    called = False

    def adj(products: list[CatalogProduct], total: Decimal) -> list[Adjustment]:
        nonlocal called
        called = True
        return [Adjustment(id="x", description="x", amount=Decimal("1"))]

    products = [_p("10.00", "10.00", removed=True)]  # the only member is excluded
    s = evaluate_cart("scraper_specific", products, adj)
    assert called is False
    assert s.adjustments == []
    assert s.final_price == Decimal(0)


def test_cross_ignores_adjuster() -> None:
    def adj(products: list[CatalogProduct], total: Decimal) -> list[Adjustment]:
        return [Adjustment(id="x", description="x", amount=Decimal("1"))]

    s = evaluate_cart("cross", [_p("10.00", "10.00")], adj)
    assert s.adjustments == []
    assert s.final_price == Decimal("10.00")


def test_threshold_reached_and_not_reached() -> None:
    products = [_p("10.00", "12.00"), _p("20.00", "20.00")]  # discounted total 30
    reached = evaluate_cart("cross", products, threshold_amount=Decimal("30.00"))
    assert reached.threshold is not None
    assert reached.threshold.current == Decimal("30.00")
    assert reached.threshold.reached is True
    assert reached.threshold.partial is False

    not_reached = evaluate_cart("cross", products, threshold_amount=Decimal("25.00"))
    assert not_reached.threshold is not None
    assert not_reached.threshold.reached is False


def test_threshold_partial_when_members_excluded() -> None:
    products = [_p("10.00", "10.00"), _p("99.00", "99.00", removed=True)]
    s = evaluate_cart("cross", products, threshold_amount=Decimal("10.00"))
    assert s.threshold is not None
    assert s.threshold.reached is True
    assert s.threshold.partial is True  # reached, but a delisted member is excluded


def test_no_threshold_without_active_members() -> None:
    products = [_p("10.00", "10.00", available=False)]  # only member excluded
    s = evaluate_cart("cross", products, threshold_amount=Decimal("5.00"))
    assert s.threshold is None  # CART-R12
