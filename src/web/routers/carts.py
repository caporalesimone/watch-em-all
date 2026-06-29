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
from src.core.models import Cart, CartMember
from src.core.plugins.base import ScraperPlugin
from src.core.plugins.registry import LoadedPlugin
from src.web.deps import SessionDep, UserDep
from src.web.schemas import CartCreate, CartOut, CartPatch

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
