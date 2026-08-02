"""The admin dashboard (10.B9): how big is this installation, and is it delivering.

**Counts only, never content** (DASH-R6). The admin governs the installation; they do not
read anybody's carts, and nothing here would let them. Every number below is a `COUNT`, and
the closest it gets to a person is how many accounts exist in each state.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from src.core.models import (
    AlertDelivery,
    AlertLog,
    Cart,
    CatalogProduct,
    PriceHistory,
    ScraperSchedule,
    User,
)
from src.web.deps import AdminDep, SessionDep
from src.web.schemas import DashboardNotifications, DashboardResponse, DashboardTotals

router = APIRouter(prefix="/admin", tags=["Admin: dashboard"])


@router.get(
    "/dashboard",
    response_model=DashboardResponse,
    summary="System-wide totals and delivery health (admin only).",
)
def dashboard(
    _admin: AdminDep,
    db: SessionDep,
    window_days: Annotated[int, Query(ge=1, le=365)] = 7,
) -> DashboardResponse:
    def count(model: type, *where: object) -> int:
        return int(db.scalar(select(func.count()).select_from(model).where(*where)) or 0)  # type: ignore[arg-type]

    totals = DashboardTotals(
        users_total=count(User),
        # The three states do not add up to the total on purpose: an account marked for
        # deletion is also inactive, and counting it twice would be the honest arithmetic of
        # two different questions rather than a partition.
        users_active=count(User, User.is_active.is_(True), User.deletion_marked_at.is_(None)),
        users_deleting=count(User, User.deletion_marked_at.is_not(None)),
        products_total=count(CatalogProduct),
        products_delisted=count(CatalogProduct, CatalogProduct.removed.is_(True)),
        carts_total=count(Cart),
        # The one number that only grows: it is the value the system accumulates, and the
        # only table the maintenance never prunes (MNT-R2).
        price_history_rows=count(PriceHistory),
        watched_scrapers=count(ScraperSchedule, ScraperSchedule.enabled.is_(True)),
    )

    since = datetime.now(tz=UTC) - timedelta(days=window_days)
    # Deliveries are counted through their alert, not by their own timestamp: a delivery that
    # sat pending across midnight belongs to the digest that produced it, which is the run an
    # admin would go looking for.
    recent = select(AlertLog.id).where(AlertLog.created_at >= since).scalar_subquery()

    def deliveries(status: str) -> int:
        return int(
            db.scalar(
                select(func.count())
                .select_from(AlertDelivery)
                .where(AlertDelivery.alert_log_id.in_(recent), AlertDelivery.status == status)
            )
            or 0
        )

    return DashboardResponse(
        totals=totals,
        notifications=DashboardNotifications(
            window_days=window_days,
            alerts=count(AlertLog, AlertLog.created_at >= since),
            delivered=deliveries("delivered"),
            failed=deliveries("failed"),
            # Both "skipped" shapes are one number here: from the dashboard's altitude the
            # question is "did it go out", and "no channel configured" and "channel off" are
            # the same answer to it.
            skipped=deliveries("skipped") + deliveries("skipped_no_notifier"),
        ),
    )
