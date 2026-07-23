"""Unit tests for the price-history read side (price_history.py, HISTC-R4). Phase 8.

Pure service-level: an in-memory SQLite session, PriceHistory rows inserted directly with
explicit ``recorded_at`` so the range windows and the pre-range entry can be asserted precisely.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from src.core.models import PriceHistory
from src.core.price_history import product_series

PRODUCT = 1
USER = 1


@pytest.fixture()
def session() -> Iterator[Session]:
    from src.core.db import create_schema, init_engine, new_session

    init_engine("sqlite+pysqlite:///:memory:")
    create_schema()
    s = new_session()
    try:
        yield s
    finally:
        s.close()


def _hist(
    session: Session,
    *,
    days_ago: float,
    price: str,
    available: bool = True,
    product_id: int = PRODUCT,
) -> None:
    session.add(
        PriceHistory(
            product_id=product_id,
            user_id=USER,
            price_current=Decimal(price),
            price_original=Decimal(price),
            discount_pct=Decimal("0.00"),
            is_available=available,
            recorded_at=datetime.now(UTC) - timedelta(days=days_ago),
        )
    )
    session.commit()


def test_empty_product_returns_no_points(session: Session) -> None:
    assert product_series(session, PRODUCT, "all") == []


def test_all_returns_every_point_oldest_first(session: Session) -> None:
    _hist(session, days_ago=40, price="40.00")
    _hist(session, days_ago=20, price="30.00")
    _hist(session, days_ago=2, price="25.00")

    series = product_series(session, PRODUCT, "all")

    assert [str(p.price) for p in series] == ["40.00", "30.00", "25.00"]
    assert series[0].t < series[1].t < series[2].t


def test_week_keeps_only_the_window_plus_clamped_pre_entry(session: Session) -> None:
    _hist(session, days_ago=40, price="40.00")  # well before the window
    _hist(session, days_ago=20, price="30.00")  # the last change BEFORE the 7-day window
    _hist(session, days_ago=2, price="25.00")  # inside the window

    series = product_series(session, PRODUCT, "week")

    # Only the nearest pre-window entry (30.00) is carried in, not the older 40.00.
    assert [str(p.price) for p in series] == ["30.00", "25.00"]
    # The carried-in point is clamped to the window start (~7 days ago), not its real age.
    cutoff = datetime.now(UTC) - timedelta(days=7)
    assert abs((series[0].t - cutoff).total_seconds()) < 5


def test_month_window_includes_the_pre_entry(session: Session) -> None:
    _hist(session, days_ago=40, price="40.00")  # before the 30-day window
    _hist(session, days_ago=20, price="30.00")  # inside
    _hist(session, days_ago=2, price="25.00")  # inside

    series = product_series(session, PRODUCT, "month")

    assert [str(p.price) for p in series] == ["40.00", "30.00", "25.00"]


def test_availability_flag_is_preserved(session: Session) -> None:
    _hist(session, days_ago=5, price="20.00", available=True)
    _hist(session, days_ago=3, price="20.00", available=False)  # went out of stock
    _hist(session, days_ago=1, price="22.00", available=True)  # back in stock

    series = product_series(session, PRODUCT, "week")

    assert [p.available for p in series] == [True, False, True]


def test_other_products_are_not_mixed_in(session: Session) -> None:
    _hist(session, days_ago=1, price="10.00", product_id=PRODUCT)
    _hist(session, days_ago=1, price="99.00", product_id=2)

    series = product_series(session, PRODUCT, "all")

    assert [str(p.price) for p in series] == ["10.00"]
