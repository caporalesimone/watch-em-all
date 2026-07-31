"""Product read API (price-history.md). Phase 8: GET /api/products/{id}/history.

The stepped price series for one of the current user's products, served ready for the chart
(the SPA does not aggregate, HISTC-R4). Per-user (DB-R1): a product the user does not own is a
404, never another user's data. Writing history is never done here — it is appended by the
Catalog Update Service on every scrape.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import select

from src.core.errors import APIError
from src.core.models import CatalogProduct
from src.core.price_history import Range, product_series
from src.web.deps import SessionDep, UserDep
from src.web.schemas import PricePoint, ProductHistory

router = APIRouter(prefix="/products", tags=["Products"])


@router.get(
    "/{product_id}/history",
    response_model=ProductHistory,
    summary="Stepped price/availability series for one of the user's products.",
)
def product_history(
    product_id: int,
    user: UserDep,
    db: SessionDep,
    range: Annotated[Range, Query(description="time window: week=7d, month=30d, all")] = "month",
) -> ProductHistory:
    # The identity, not just the ownership: the history is the product's and is shared by
    # everyone watching it, so the series is fetched by (plugin_id, external_id). Ownership of
    # *a row* with that identity is still what grants access to it.
    owned = db.execute(
        select(CatalogProduct.plugin_id, CatalogProduct.external_id).where(
            CatalogProduct.id == product_id, CatalogProduct.user_id == user.sub
        )
    ).first()
    if owned is None:
        raise APIError(404, "product_not_found", "product not found")

    series = product_series(db, owned.plugin_id, owned.external_id, range)
    return ProductHistory(
        product_id=product_id,
        range=range,
        points=[PricePoint(t=p.t, price=p.price, available=p.available) for p in series],
    )
