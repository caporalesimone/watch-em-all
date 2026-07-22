"""Unit tests for the product diff (phase 6.B4) — the normative cases from alert-engine.md.

Pure tests on ``diff_products``: current members vs a baseline snapshot, filtered to the
enabled types. All-time-low is out of scope (phase 11).
"""

from __future__ import annotations

from decimal import Decimal

from src.core.alert_engine import diff_products
from src.core.contracts import AlertType
from src.core.models import CatalogProduct

# Every product tag enabled, so the tests exercise the diff itself (filtering is a
# separate case below).
ALL_PRODUCT_TAGS = {
    AlertType.PRODUCT_ON_SALE,
    AlertType.PRODUCT_OFF_SALE,
    AlertType.PRODUCT_UNAVAILABLE,
    AlertType.PRODUCT_AVAILABLE_AGAIN,
}


def _product(
    pid: int, *, price: str, discount: str, available: bool = True, removed: bool = False
) -> CatalogProduct:
    return CatalogProduct(
        id=pid,
        price_current=Decimal(price),
        discount_pct=Decimal(discount),
        is_available=available,
        removed=removed,
    )


def _prev(*, on_sale: bool, available: bool, price: str) -> dict[str, object]:
    return {"on_sale": on_sale, "available": available, "price_current": price}


def _snap(**products: dict[str, object]) -> dict[str, object]:
    return {"products": products, "all_on_sale": False, "threshold_reached": False}


def test_no_change_no_tags() -> None:
    # First run after seed / unchanged product: diff empty by construction.
    snap = _snap(**{"1": _prev(on_sale=False, available=True, price="100.00")})
    assert diff_products([_product(1, price="100.00", discount="0")], snap, ALL_PRODUCT_TAGS) == []


def test_entered_sale() -> None:
    snap = _snap(**{"1": _prev(on_sale=False, available=True, price="100.00")})
    diffs = diff_products([_product(1, price="80.00", discount="20")], snap, ALL_PRODUCT_TAGS)
    assert len(diffs) == 1
    assert diffs[0].tags == [AlertType.PRODUCT_ON_SALE]
    assert diffs[0].price_previous == Decimal("100.00")
    assert diffs[0].price_current == Decimal("80.00")


def test_further_drop_while_on_sale_re_alerts() -> None:
    # Already on sale at 90; drops further to 80 → ON_SALE again (ALERT-R11).
    snap = _snap(**{"1": _prev(on_sale=True, available=True, price="90.00")})
    diffs = diff_products([_product(1, price="80.00", discount="20")], snap, ALL_PRODUCT_TAGS)
    assert [t for d in diffs for t in d.tags] == [AlertType.PRODUCT_ON_SALE]


def test_same_sale_price_does_not_re_alert() -> None:
    # On sale at 80, still 80 → no new event (diff vs baseline, not vs scrape).
    snap = _snap(**{"1": _prev(on_sale=True, available=True, price="80.00")})
    assert diff_products([_product(1, price="80.00", discount="20")], snap, ALL_PRODUCT_TAGS) == []


def test_left_sale() -> None:
    snap = _snap(**{"1": _prev(on_sale=True, available=True, price="80.00")})
    diffs = diff_products([_product(1, price="100.00", discount="0")], snap, ALL_PRODUCT_TAGS)
    assert [t for d in diffs for t in d.tags] == [AlertType.PRODUCT_OFF_SALE]


def test_became_unavailable_and_available_again() -> None:
    snap = _snap(**{"1": _prev(on_sale=False, available=True, price="100.00")})
    gone = diff_products(
        [_product(1, price="100.00", discount="0", available=False)], snap, ALL_PRODUCT_TAGS
    )
    assert gone[0].tags == [AlertType.PRODUCT_UNAVAILABLE]

    snap2 = _snap(**{"1": _prev(on_sale=False, available=False, price="100.00")})
    back = diff_products([_product(1, price="100.00", discount="0")], snap2, ALL_PRODUCT_TAGS)
    assert back[0].tags == [AlertType.PRODUCT_AVAILABLE_AGAIN]


def test_available_again_and_on_sale_combine() -> None:
    # Came back in stock AND on sale → both tags on the same product.
    snap = _snap(**{"1": _prev(on_sale=False, available=False, price="100.00")})
    diffs = diff_products([_product(1, price="80.00", discount="20")], snap, ALL_PRODUCT_TAGS)
    assert set(diffs[0].tags) == {AlertType.PRODUCT_AVAILABLE_AGAIN, AlertType.PRODUCT_ON_SALE}


def test_new_member_is_silent() -> None:
    # A product not in the baseline was seeded silently → no event this run.
    new = [_product(9, price="80.00", discount="20")]
    assert diff_products(new, _snap(), ALL_PRODUCT_TAGS) == []


def test_delisted_member_ignored() -> None:
    snap = _snap(**{"1": _prev(on_sale=False, available=True, price="100.00")})
    diffs = diff_products(
        [_product(1, price="80.00", discount="20", removed=True)], snap, ALL_PRODUCT_TAGS
    )
    assert diffs == []


def test_only_enabled_tags_survive() -> None:
    # Entered sale, but ON_SALE not enabled → nothing.
    snap = _snap(**{"1": _prev(on_sale=False, available=True, price="100.00")})
    diffs = diff_products(
        [_product(1, price="80.00", discount="20")], snap, {AlertType.PRODUCT_UNAVAILABLE}
    )
    assert diffs == []
