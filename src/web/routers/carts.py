"""Carts API (carts.md, cart-engine.md). Phase 5.

5.B1 — the CRUD skeleton: create/list/get/rename/delete a cart, scoped to the
token's user (DB-R1). ``mode`` is fixed at creation (CART-R2): a ``scraper_specific``
cart names a loaded scraper, a ``cross`` cart names none. Membership (items) is
5.B2; the computed state (totals, adjustments, threshold) is layered on by the
Cart Engine in 5.B3 — for now ``CartOut`` reports only identity + member count.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy import func, select

from src.core.errors import APIError
from src.core.models import Cart, CartMember, CatalogProduct
from src.core.plugins.base import ScraperPlugin
from src.core.plugins.registry import LoadedPlugin
from src.web.deps import SessionDep, UserDep
from src.web.schemas import CartCreate, CartItemsBody, CartOut, CartPatch

router = APIRouter(prefix="/carts", tags=["Carts"])


def _loaded_scraper_ids(request: Request) -> set[str]:
    """plugin_id of every loaded scraper — the valid targets for a scraper_specific cart."""
    loaded: list[LoadedPlugin] = list(getattr(request.app.state, "loaded_plugins", []))
    return {lp.plugin.plugin_id for lp in loaded if isinstance(lp.plugin, ScraperPlugin)}


def _member_count(db: SessionDep, cart_id: int) -> int:
    return (
        db.scalar(select(func.count()).select_from(CartMember).where(CartMember.cart_id == cart_id))
        or 0
    )


def _out(db: SessionDep, cart: Cart) -> CartOut:
    return CartOut(
        id=cart.id,
        name=cart.name,
        mode=cart.mode,
        scraper_id=cart.scraper_id,
        threshold_pct=cart.threshold_pct,
        member_count=_member_count(db, cart.id),
        created_at=cart.created_at,
    )


def _get_owned(db: SessionDep, user: UserDep, cart_id: int) -> Cart:
    """The user's cart or 404 — never reveal another user's cart (DB-R1)."""
    cart = db.scalar(select(Cart).where(Cart.id == cart_id, Cart.user_id == user.sub))
    if cart is None:
        raise APIError(404, "cart_not_found", "cart not found")
    return cart


@router.get("", response_model=list[CartOut], summary="List the current user's carts.")
def list_carts(user: UserDep, db: SessionDep) -> list[CartOut]:
    carts = db.scalars(
        select(Cart)
        .where(Cart.user_id == user.sub)
        .order_by(Cart.created_at.desc(), Cart.id.desc())
    ).all()
    return [_out(db, c) for c in carts]


@router.post("", response_model=CartOut, status_code=201, summary="Create a cart (mode is fixed).")
def create_cart(body: CartCreate, user: UserDep, db: SessionDep, request: Request) -> CartOut:
    if body.mode == "scraper_specific":
        if not body.scraper_id:
            raise APIError(
                422, "scraper_id_required", "scraper_specific carts require a scraper_id"
            )
        if body.scraper_id not in _loaded_scraper_ids(request):
            raise APIError(422, "unknown_scraper", f"no loaded scraper {body.scraper_id!r}")
        scraper_id = body.scraper_id
    else:  # cross
        if body.scraper_id:
            raise APIError(422, "scraper_id_not_allowed", "cross carts must not name a scraper")
        scraper_id = None

    cart = Cart(user_id=user.sub, name=body.name, mode=body.mode, scraper_id=scraper_id)
    db.add(cart)
    db.commit()
    db.refresh(cart)
    return _out(db, cart)


@router.get("/{cart_id}", response_model=CartOut, summary="Get one cart.")
def get_cart(cart_id: int, user: UserDep, db: SessionDep) -> CartOut:
    return _out(db, _get_owned(db, user, cart_id))


@router.patch("/{cart_id}", response_model=CartOut, summary="Rename a cart (mode is immutable).")
def patch_cart(cart_id: int, body: CartPatch, user: UserDep, db: SessionDep) -> CartOut:
    cart = _get_owned(db, user, cart_id)
    if body.name is not None:
        cart.name = body.name
    db.commit()
    db.refresh(cart)
    return _out(db, cart)


@router.delete("/{cart_id}", status_code=204, summary="Delete a cart (only the cart, CART-R3).")
def delete_cart(cart_id: int, user: UserDep, db: SessionDep) -> None:
    cart = _get_owned(db, user, cart_id)
    db.delete(cart)  # cart_members cascade; catalog products are untouched
    db.commit()


def _cart_currencies(db: SessionDep, cart_id: int) -> set[str]:
    """Distinct currencies of the cart's current members (CART single-currency)."""
    return set(
        db.scalars(
            select(CatalogProduct.currency)
            .join(CartMember, CartMember.product_id == CatalogProduct.id)
            .where(CartMember.cart_id == cart_id)
        ).all()
    )


@router.post(
    "/{cart_id}/items", response_model=CartOut, summary="Add catalog products to a cart (5.B2)."
)
def add_items(cart_id: int, body: CartItemsBody, user: UserDep, db: SessionDep) -> CartOut:
    cart = _get_owned(db, user, cart_id)
    ids = list(dict.fromkeys(body.product_ids))  # dedupe, preserve order

    # All ids must be the user's catalog products (CART-R1).
    products = db.scalars(
        select(CatalogProduct).where(CatalogProduct.user_id == user.sub, CatalogProduct.id.in_(ids))
    ).all()
    by_id = {p.id: p for p in products}
    missing = [i for i in ids if i not in by_id]
    if missing:
        raise APIError(422, "product_not_found", f"not in your catalog: {missing}")

    ordered = [by_id[i] for i in ids]

    # Delisted products are not currently offered → cannot be added (out-of-stock can).
    delisted = [p.id for p in ordered if p.removed]
    if delisted:
        raise APIError(422, "product_delisted", f"delisted products cannot be added: {delisted}")

    # scraper_specific accepts only products of its own scraper (CART-R4).
    if cart.mode == "scraper_specific":
        wrong = [p.id for p in ordered if p.plugin_id != cart.scraper_id]
        if wrong:
            raise APIError(422, "product_scraper_mismatch", f"not from {cart.scraper_id}: {wrong}")

    # A cart holds a single currency (decision 2026-06-29): the existing members plus
    # the new products must share exactly one currency.
    currencies = _cart_currencies(db, cart.id) | {p.currency for p in ordered}
    if len(currencies) > 1:
        raise APIError(422, "currency_mismatch", f"a cart holds one currency: {sorted(currencies)}")

    # Idempotent: skip ids already members; add the rest.
    existing = set(
        db.scalars(
            select(CartMember.product_id).where(
                CartMember.cart_id == cart.id, CartMember.product_id.in_(ids)
            )
        ).all()
    )
    for pid in ids:
        if pid not in existing:
            db.add(CartMember(cart_id=cart.id, product_id=pid))
    db.commit()
    return _out(db, cart)


@router.delete(
    "/{cart_id}/items", response_model=CartOut, summary="Remove cart members (no-op if absent)."
)
def remove_items(cart_id: int, body: CartItemsBody, user: UserDep, db: SessionDep) -> CartOut:
    cart = _get_owned(db, user, cart_id)
    members = db.scalars(
        select(CartMember).where(
            CartMember.cart_id == cart.id, CartMember.product_id.in_(body.product_ids)
        )
    ).all()
    for m in members:  # absent ids are a no-op
        db.delete(m)
    db.commit()
    return _out(db, cart)
