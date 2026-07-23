"""Price-history read side — series for the charts (price-history.md, HISTC-R4). Phase 8.

The append-only ``price_history`` table (written by the Catalog Update Service on every
price/availability change) is read here into a chart-ready series. Entries are change points:
the chart draws them as a step line (the value holds between two changes) with an explicit gap
wherever the product was unavailable — nothing is interpolated. For a bounded range (week/month)
the series also carries the value in effect at the window start, so the line starts at the right
price instead of at zero (that pre-range entry is clamped to the window start).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.models import PriceHistory

Range = Literal["week", "month", "all"]

_RANGE_DAYS: dict[Range, int | None] = {"week": 7, "month": 30, "all": None}


@dataclass(frozen=True)
class SeriesPoint:
    """One point of a price series: the discounted price and availability at ``t``."""

    t: datetime
    price: Decimal
    available: bool


def product_series(session: Session, product_id: int, range_: Range) -> list[SeriesPoint]:
    """The stepped price series for a product over ``range_``, ordered oldest → newest.

    Ownership is enforced by the caller (the router 404s a product the user does not own); this
    reads by ``product_id`` alone. For week/month the window is ``[now - N days, now]`` and the
    last entry before the window is prepended, clamped to the window start (HISTC-R4).
    """
    ordered = (
        select(PriceHistory)
        .where(PriceHistory.product_id == product_id)
        .order_by(PriceHistory.recorded_at.asc(), PriceHistory.id.asc())
    )

    days = _RANGE_DAYS[range_]
    if days is None:
        return [_point(r) for r in session.scalars(ordered).all()]

    cutoff = datetime.now(UTC) - timedelta(days=days)
    within = session.scalars(ordered.where(PriceHistory.recorded_at >= cutoff)).all()

    # The value in effect at the window start = the last change strictly before it. Clamp its
    # timestamp to the window start so the step line begins at the edge, not before it.
    before = session.scalar(
        select(PriceHistory)
        .where(PriceHistory.product_id == product_id, PriceHistory.recorded_at < cutoff)
        .order_by(PriceHistory.recorded_at.desc(), PriceHistory.id.desc())
        .limit(1)
    )

    points = [_point(r) for r in within]
    if before is not None:
        points.insert(
            0,
            SeriesPoint(t=cutoff, price=before.price_current, available=before.is_available),
        )
    return points


def _point(row: PriceHistory) -> SeriesPoint:
    return SeriesPoint(t=row.recorded_at, price=row.price_current, available=row.is_available)
