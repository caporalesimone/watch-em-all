"""Unit tests for the cart-event diff (phase 6.B5) — normative cases from alert-engine.md.

``diff_cart_events``: all-on-sale and threshold transitions vs the baseline, with the
zero-active guard and enabled-type filtering.
"""

from __future__ import annotations

from decimal import Decimal

from src.core.alert_engine import diff_cart_events
from src.core.cart_engine import CartState, ThresholdState
from src.core.contracts import AlertType

CART_TAGS = {
    AlertType.CART_ALL_ON_SALE,
    AlertType.CART_THRESHOLD_REACHED,
    AlertType.CART_THRESHOLD_REACHED_PARTIAL,
}


def _state(
    *, all_on_sale: bool, reached: bool | None = None, partial: bool = False, active: int = 1
) -> CartState:
    threshold = None
    if reached is not None:
        threshold = ThresholdState(
            amount=Decimal("50"), current=Decimal("40"), reached=reached, partial=partial
        )
    return CartState(
        currency="EUR",
        total_full=Decimal("0"),
        total_discounted=Decimal("0"),
        adjustments=[],
        final_price=Decimal("0"),
        active_count=active,
        excluded_count=0,
        has_delisted=False,
        any_on_sale=all_on_sale,
        all_on_sale=all_on_sale,
        threshold=threshold,
    )


def _snap(*, all_on_sale: bool = False, threshold_reached: bool = False) -> dict[str, object]:
    return {"products": {}, "all_on_sale": all_on_sale, "threshold_reached": threshold_reached}


def test_all_on_sale_transition() -> None:
    got = diff_cart_events(_state(all_on_sale=True), _snap(all_on_sale=False), CART_TAGS)
    assert got == [AlertType.CART_ALL_ON_SALE]


def test_all_on_sale_no_repeat() -> None:
    # Already all-on-sale at the baseline → no new event.
    assert diff_cart_events(_state(all_on_sale=True), _snap(all_on_sale=True), CART_TAGS) == []


def test_threshold_reached() -> None:
    got = diff_cart_events(_state(all_on_sale=False, reached=True), _snap(), CART_TAGS)
    assert got == [AlertType.CART_THRESHOLD_REACHED]


def test_threshold_reached_partial() -> None:
    got = diff_cart_events(
        _state(all_on_sale=False, reached=True, partial=True), _snap(), CART_TAGS
    )
    assert got == [AlertType.CART_THRESHOLD_REACHED_PARTIAL]


def test_threshold_no_repeat_until_it_rises_and_falls() -> None:
    # Reached already at the baseline → nothing new.
    snap = _snap(threshold_reached=True)
    assert diff_cart_events(_state(all_on_sale=False, reached=True), snap, CART_TAGS) == []


def test_threshold_not_reached_no_event() -> None:
    assert diff_cart_events(_state(all_on_sale=False, reached=False), _snap(), CART_TAGS) == []


def test_only_enabled_events() -> None:
    # Threshold reached but the user only enabled all-on-sale → nothing.
    got = diff_cart_events(
        _state(all_on_sale=False, reached=True), _snap(), {AlertType.CART_ALL_ON_SALE}
    )
    assert got == []


def test_no_active_members_is_guarded() -> None:
    # No active members: all_on_sale False and threshold None (CART-R12) → no events.
    empty = _state(all_on_sale=False, reached=None, active=0)
    assert diff_cart_events(empty, _snap(), CART_TAGS) == []


def test_all_on_sale_and_threshold_together() -> None:
    got = diff_cart_events(_state(all_on_sale=True, reached=True), _snap(), CART_TAGS)
    assert set(got) == {AlertType.CART_ALL_ON_SALE, AlertType.CART_THRESHOLD_REACHED}
