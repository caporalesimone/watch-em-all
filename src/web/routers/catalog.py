"""Catalog API (catalog-and-product-picker.md): read in phase 3, cleanups in phase 9.

Returns the current user's catalog only (multi-tenancy DB-R1: scoped to the token's user),
paginated, sortable and filterable. Products are never *written* here — that is the Catalog
Update Service's job, reached through a scrape — but they can be **removed** (9.B7), which is a
different thing: the user is throwing rows away, not describing what a site offers.

A removal cascades to ``cart_members`` (``ON DELETE CASCADE``, CART-R8/CAT-R8), so deleting a
product also takes it out of every cart holding it — which these endpoints have to be honest
about. It does **not** touch ``price_history``: that chain is keyed on the product's identity
and shared by everyone watching it, so it is not this user's to delete, and a product removed
today keeps the past it will hand to whoever watches it next.

Nothing here touches the **watches** either: those are a separate list with their own Remove,
and the visible consequence — deleting a product you still watch brings it back on the next run
— is accepted rather than hidden (decision 2026-07-29).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from src.core.contracts import BrandRef, CategoryRef
from src.core.errors import APIError
from src.core.models import CatalogProduct, ProductSource
from src.web.deps import SessionDep, UserDep
from src.web.schemas import CatalogItem, CatalogItemSource, CatalogPage, RemovedCount

router = APIRouter(prefix="/catalog", tags=["Catalog"])

_SORT_COLUMNS: dict[str, InstrumentedAttribute[Any]] = {
    "name": CatalogProduct.name,
    "plugin_id": CatalogProduct.plugin_id,  # "source"
    "price_current": CatalogProduct.price_current,
    "price_original": CatalogProduct.price_original,  # "list price"
    "is_available": CatalogProduct.is_available,  # "availability"
    "last_seen_at": CatalogProduct.last_seen_at,
}


def _sources_for(db: Session, product_ids: list[int]) -> dict[int, list[CatalogItemSource]]:
    """The provenance of a whole page in one query (C14). One query for the page rather than one
    per row: this feeds a list of up to a hundred products."""
    if not product_ids:
        return {}
    out: dict[int, list[CatalogItemSource]] = {}
    rows = db.scalars(
        select(ProductSource)
        .where(ProductSource.product_id.in_(product_ids))
        .order_by(ProductSource.id.asc())
    ).all()
    for row in rows:
        out.setdefault(row.product_id, []).append(
            CatalogItemSource(kind=row.source_kind, label=row.source_label)
        )
    return out


def _to_item(row: CatalogProduct, sources: list[CatalogItemSource]) -> CatalogItem:
    return CatalogItem(
        id=row.id,
        plugin_id=row.plugin_id,
        external_id=row.external_id,
        url=row.url,
        name=row.name,
        image_url=row.image_url,
        brand=BrandRef(text=row.brand_text, link=row.brand_link) if row.brand_text else None,
        tags=row.tags,
        category=[CategoryRef(**c) for c in row.category],
        currency=row.currency,
        price_current=row.price_current,
        price_original=row.price_original,
        discount_pct=row.discount_pct,
        is_available=row.is_available,
        removed=row.removed,
        extra=row.extra_json,
        first_seen_at=row.first_seen_at,
        last_seen_at=row.last_seen_at,
        sources=sources,
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

    sources = _sources_for(db, [r.id for r in rows])
    return CatalogPage(
        items=[_to_item(r, sources.get(r.id, [])) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


# --- cleanups (9.B7) -------------------------------------------------------------------
#
# Three shapes, because they answer three different intentions: "tidy up what the site no
# longer offers", "I do not want this one", "start over". Each reports how many rows went, so
# the page can say what happened instead of just refreshing.


@router.delete(
    "/delisted",
    response_model=RemovedCount,
    summary="Remove every delisted product from the current user's catalog.",
)
def remove_delisted(user: UserDep, db: SessionDep) -> RemovedCount:
    """The routine tidy-up: products a complete delivery no longer offered (9.B6 marked them,
    with the date). Their cart memberships go with them; their price history stays, because it
    belongs to the product rather than to this row."""
    rows = db.scalars(
        select(CatalogProduct).where(
            CatalogProduct.user_id == user.sub, CatalogProduct.removed.is_(True)
        )
    ).all()
    for row in rows:
        db.delete(row)  # ORM delete, so the cart/history cascades run through the mapper too
    db.commit()
    return RemovedCount(removed=len(rows))


@router.delete(
    "/{product_id}",
    response_model=RemovedCount,
    summary="Remove one product from the current user's catalog.",
)
def remove_product(product_id: int, user: UserDep, db: SessionDep) -> RemovedCount:
    row = db.scalar(
        select(CatalogProduct).where(
            CatalogProduct.id == product_id, CatalogProduct.user_id == user.sub
        )
    )
    if row is None:
        # Scoped to the user first: someone else's product must read as "not found", never as
        # "forbidden", which would confirm that it exists.
        raise APIError(404, "not_found", "product not found")
    db.delete(row)
    db.commit()
    return RemovedCount(removed=1)


@router.delete(
    "", response_model=RemovedCount, summary="Empty the current user's catalog completely."
)
def empty_catalog(user: UserDep, db: SessionDep) -> RemovedCount:
    """Start over. The watches survive, so the next run refills what is still watched — which
    is why the confirmation in the UI has to say so (9.F4)."""
    rows = db.scalars(select(CatalogProduct).where(CatalogProduct.user_id == user.sub)).all()
    for row in rows:
        db.delete(row)
    db.commit()
    return RemovedCount(removed=len(rows))
