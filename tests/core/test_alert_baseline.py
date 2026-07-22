"""Unit tests for the alert baseline (phase 6.B2): snapshot payload + persistence.

Pure tests on a local in-memory engine — no web app. Cover the snapshot shape
(delisted excluded, per-product flags, cart-level flags) and upsert/get/delete.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from src.core import models  # noqa: F401  (register models on Base.metadata)
from src.core.alert_engine import delete_snapshot, get_snapshot, snapshot_payload, upsert_snapshot
from src.core.cart_engine import CartState, ThresholdState
from src.core.db import Base
from src.core.models import CatalogProduct


def _product(
    pid: int, *, price: str, discount: str, available: bool, removed: bool
) -> CatalogProduct:
    return CatalogProduct(
        id=pid,
        price_current=Decimal(price),
        discount_pct=Decimal(discount),
        is_available=available,
        removed=removed,
    )


def _state(*, all_on_sale: bool, reached: bool | None) -> CartState:
    threshold = None
    if reached is not None:
        threshold = ThresholdState(
            amount=Decimal("50"), current=Decimal("40"), reached=reached, partial=False
        )
    return CartState(
        currency="EUR",
        total_full=Decimal("0"),
        total_discounted=Decimal("0"),
        adjustments=[],
        final_price=Decimal("0"),
        active_count=0,
        excluded_count=0,
        has_delisted=False,
        any_on_sale=False,
        all_on_sale=all_on_sale,
        threshold=threshold,
    )


def test_snapshot_payload_shape() -> None:
    products = [
        _product(1, price="9.99", discount="10", available=True, removed=False),  # on sale
        _product(2, price="20.00", discount="0", available=False, removed=False),  # off sale, oos
        _product(3, price="5.00", discount="50", available=True, removed=True),  # delisted
    ]
    payload = snapshot_payload(products, _state(all_on_sale=False, reached=True))

    assert set(payload["products"].keys()) == {"1", "2"}  # delisted product 3 excluded (ALERT-R12)
    assert payload["products"]["1"] == {"on_sale": True, "available": True, "price_current": "9.99"}
    assert payload["products"]["2"] == {
        "on_sale": False,
        "available": False,
        "price_current": "20.00",
    }
    assert payload["all_on_sale"] is False
    assert payload["threshold_reached"] is True


def test_no_threshold_means_not_reached() -> None:
    payload = snapshot_payload([], _state(all_on_sale=True, reached=None))
    assert payload["products"] == {}
    assert payload["all_on_sale"] is True
    assert payload["threshold_reached"] is False


def test_upsert_get_delete_roundtrip() -> None:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        assert get_snapshot(db, 1, 1) is None

        upsert_snapshot(
            db, 1, 1, {"products": {}, "all_on_sale": False, "threshold_reached": False}
        )
        db.commit()
        row = get_snapshot(db, 1, 1)
        assert row is not None and row.snapshot_json["all_on_sale"] is False

        # Advance: same (user, cart) is updated, not duplicated.
        upsert_snapshot(
            db, 1, 1, {"products": {"7": {}}, "all_on_sale": True, "threshold_reached": True}
        )
        db.commit()
        row = get_snapshot(db, 1, 1)
        assert row is not None and row.snapshot_json["all_on_sale"] is True
        assert list(row.snapshot_json["products"].keys()) == ["7"]

        delete_snapshot(db, 1, 1)
        db.commit()
        assert get_snapshot(db, 1, 1) is None
