"""Catalog read API (catalog-and-product-picker.md). Phase 3: GET /api/catalog.

Returns the current user's catalog only (multi-tenancy DB-R1: scoped to the
token's user), paginated, sortable and filterable. Writing the catalog is never
done here — that is the Catalog Update Service's job, reached through a scrape.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import InstrumentedAttribute

from src.core.contracts import BrandRef
from src.core.models import CatalogProduct
from src.web.deps import SessionDep, UserDep
from src.web.schemas import CatalogItem, CatalogPage

router = APIRouter(prefix="/catalog", tags=["Catalog"])

_SORT_COLUMNS: dict[str, InstrumentedAttribute[Any]] = {
    "name": CatalogProduct.name,
    "plugin_id": CatalogProduct.plugin_id,  # "source"
    "price_current": CatalogProduct.price_current,
    "price_original": CatalogProduct.price_original,  # "list price"
    "discount_pct": CatalogProduct.discount_pct,
    "is_available": CatalogProduct.is_available,  # "availability"
    "last_seen_at": CatalogProduct.last_seen_at,
}


def _to_item(row: CatalogProduct) -> CatalogItem:
    return CatalogItem(
        id=row.id,
        plugin_id=row.plugin_id,
        external_id=row.external_id,
        url=row.url,
        name=row.name,
        image_url=row.image_url,
        brand=BrandRef(text=row.brand_text, link=row.brand_link) if row.brand_text else None,
        product_properties=row.product_properties,
        currency=row.currency,
        price_current=row.price_current,
        price_original=row.price_original,
        discount_pct=row.discount_pct,
        is_available=row.is_available,
        removed=row.removed,
        extra=row.extra_json,
        first_seen_at=row.first_seen_at,
        last_seen_at=row.last_seen_at,
    )


@router.get("", response_model=CatalogPage, summary="List the current user's catalog.")
def list_catalog(
    user: UserDep,
    db: SessionDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    sort: Literal[
        "name",
        "plugin_id",
        "price_current",
        "price_original",
        "discount_pct",
        "is_available",
        "last_seen_at",
    ] = "last_seen_at",
    order: Literal["asc", "desc"] = "desc",
    q: Annotated[str | None, Query(description="case-insensitive name search")] = None,
    available: Annotated[bool | None, Query(description="filter by availability")] = None,
    removed: Annotated[bool | None, Query(description="filter delisted rows")] = None,
) -> CatalogPage:
    filters: list[ColumnElement[bool]] = [CatalogProduct.user_id == user.sub]
    if q:
        filters.append(CatalogProduct.name.ilike(f"%{q}%"))
    if available is not None:
        filters.append(CatalogProduct.is_available == available)
    if removed is not None:
        filters.append(CatalogProduct.removed == removed)

    total = db.scalar(select(func.count()).select_from(CatalogProduct).where(*filters)) or 0

    column = _SORT_COLUMNS[sort]
    ordering = column.desc() if order == "desc" else column.asc()
    rows = db.scalars(
        select(CatalogProduct)
        .where(*filters)
        .order_by(ordering, CatalogProduct.id.asc())  # id tiebreaker = stable paging
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    return CatalogPage(
        items=[_to_item(r) for r in rows], total=total, page=page, page_size=page_size
    )
