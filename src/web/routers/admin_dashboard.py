"""The admin dashboard (10.B9): how big is this installation, and is it delivering.

**Counts only, never content** (DASH-R6). The admin governs the installation; they do not
read anybody's carts, and nothing here would let them. Every number below is a `COUNT`, and
the closest it gets to a person is how many accounts exist in each state.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from src.core.models import (
    AlertDelivery,
    AlertLog,
    Cart,
    CatalogProduct,
    PriceHistory,
    ScraperSchedule,
    ScrapeRun,
    ScrapeUserLog,
    User,
)
from src.web.deps import AdminDep, SessionDep
from src.web.schemas import (
    DashboardNotifications,
    DashboardResponse,
    DashboardTotals,
    DashboardUsers,
    UserLoadRow,
)

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


@router.get(
    "/dashboard/users",
    response_model=DashboardUsers,
    summary="Per-account load: how much work each person's watches cost (admin only).",
)
def dashboard_users(
    _admin: AdminDep,
    db: SessionDep,
    window_days: Annotated[int, Query(ge=1, le=365)] = 7,
) -> DashboardUsers:
    """Who is generating the traffic, and against which store.

    Still counts only (DASH-R6): a username and some numbers. "This account costs 900
    requests a week" is a governance question; *what* it is watching is not the admin's.
    """
    since = datetime.now(tz=UTC) - timedelta(days=window_days)

    # Owned rows, which have no time window: a catalog is a current state, not an event.
    products: dict[Any, Any] = {
        uid: n
        for uid, n in db.execute(
            select(CatalogProduct.user_id, func.count()).group_by(CatalogProduct.user_id)
        ).all()
    }
    carts: dict[Any, Any] = {
        uid: n
        for uid, n in db.execute(select(Cart.user_id, func.count()).group_by(Cart.user_id)).all()
    }

    # Traffic, which does: it is measured out of `scrape_user_log`, and that table is pruned,
    # so the window is not a nicety — it is the only period the data can speak for.
    def traffic(*group_by: Any) -> list[Any]:
        return list(
            db.execute(
                select(
                    ScrapeUserLog.user_id,
                    *group_by,
                    func.coalesce(func.sum(ScrapeUserLog.http_requests), 0),
                    func.coalesce(func.sum(ScrapeUserLog.cache_hits), 0),
                )
                .join(ScrapeRun, ScrapeRun.run_id == ScrapeUserLog.run_id)
                .where(ScrapeRun.started_at >= since)
                .group_by(ScrapeUserLog.user_id, *group_by)
            ).all()
        )

    names: dict[Any, Any] = {
        uid: name for uid, name in db.execute(select(User.id, User.username)).all()
    }

    by_user = [
        UserLoadRow(
            user_id=int(uid),
            username=names.get(uid),
            products=int(products.get(uid, 0)),
            carts=int(carts.get(uid, 0)),
            http_requests=int(req),
            cache_hits=int(hits),
        )
        for uid, req, hits in traffic()
    ]
    # An account with watches but no run in the window still belongs on this list: "costs
    # nothing lately" is an answer, and leaving it out would read as "does not exist".
    seen = {row.user_id for row in by_user}
    by_user += [
        UserLoadRow(
            user_id=int(uid),
            username=names.get(uid),
            products=int(products.get(uid, 0)),
            carts=int(carts.get(uid, 0)),
            http_requests=0,
            cache_hits=0,
        )
        for uid in set(products) | set(carts)
        if uid not in seen
    ]
    by_user.sort(key=lambda r: (-r.http_requests, -r.products, r.user_id))

    by_pair = [
        UserLoadRow(
            user_id=int(uid),
            username=names.get(uid),
            scraper_id=str(scraper),
            products=0,  # a product belongs to a catalog, not to a (user, scraper) pair
            carts=0,
            http_requests=int(req),
            cache_hits=int(hits),
        )
        for uid, scraper, req, hits in traffic(ScrapeRun.scraper_id)
    ]
    by_pair.sort(key=lambda r: (-r.http_requests, r.user_id, r.scraper_id or ""))

    return DashboardUsers(window_days=window_days, by_user=by_user, by_user_and_scraper=by_pair)
