"""Carts API (carts.md, cart-engine.md). Phase 5.

CRUD + membership (5.B1/5.B2) plus the computed state from the Cart Engine (5.B3):
the list returns cards (totals, adjustments, health flag), the detail adds the
member rows. ``mode`` is fixed at creation (CART-R2), per-user (DB-R1). For a
scraper_specific cart the engine's adjustments come from the cart's scraper, which
the router resolves from ``app.state.loaded_plugins`` and binds — the core engine
never imports the web.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy import select

from src.core.alert_engine import delete_snapshot, snapshot_payload, upsert_snapshot
from src.core.cart_engine import CartState, evaluate_cart
from src.core.contracts import Adjustment, AlertType, BrandRef, CategoryRef
from src.core.errors import APIError
from src.core.models import Cart, CartAlertType, CartMember, CatalogProduct
from src.web.adjust import adjuster_for, loaded_scrapers
from src.web.deps import SessionDep, UserDep
from src.web.schemas import (
    CartAdjustment,
    CartAlertTypesBody,
    CartCard,
    CartCreate,
    CartDetail,
    CartItemsBody,
    CartMemberOut,
    CartPatch,
    CartThreshold,
)

router = APIRouter(prefix="/carts", tags=["Carts"])


def _get_owned(db: SessionDep, user: UserDep, cart_id: int) -> Cart:
    """The user's cart or 404 — never reveal another user's cart (DB-R1)."""
    cart = db.scalar(select(Cart).where(Cart.id == cart_id, Cart.user_id == user.sub))
    if cart is None:
        raise APIError(404, "cart_not_found", "cart not found")
    return cart


def _cart_products(db: SessionDep, cart_id: int) -> list[CatalogProduct]:
    """The catalog products that are members of the cart (CART-R1)."""
    return list(
        db.scalars(
            select(CatalogProduct)
            .join(CartMember, CartMember.product_id == CatalogProduct.id)
            .where(CartMember.cart_id == cart_id)
            .order_by(CatalogProduct.name.asc(), CatalogProduct.id.asc())
        ).all()
    )


def _alert_types(db: SessionDep, cart_id: int) -> list[str]:
    """The alert types enabled on the cart (6.B1): each row present = one type enabled,
    returned sorted for a stable payload."""
    return sorted(
        db.scalars(select(CartAlertType.alert_type).where(CartAlertType.cart_id == cart_id)).all()
    )


def _to_adjustment(a: Adjustment) -> CartAdjustment:
    return CartAdjustment(id=a.id, description=a.description, amount=a.amount, params=a.params)


def _to_threshold(state: CartState) -> CartThreshold | None:
    t = state.threshold
    if t is None:
        return None
    return CartThreshold(amount=t.amount, current=t.current, reached=t.reached, partial=t.partial)


def _member_out(p: CatalogProduct, active: bool) -> CartMemberOut:
    return CartMemberOut(
        product_id=p.id,
        plugin_id=p.plugin_id,
        external_id=p.external_id,
        url=p.url,
        name=p.name,
        image_url=p.image_url,
        brand=BrandRef(text=p.brand_text, link=p.brand_link) if p.brand_text else None,
        tags=p.tags,
        category=[CategoryRef(**c) for c in p.category],
        currency=p.currency,
        price_current=p.price_current,
        price_original=p.price_original,
        discount_pct=p.discount_pct,
        is_available=p.is_available,
        removed=p.removed,
        active=p.is_available and not p.removed,
    )


def _state(db: SessionDep, request: Request, cart: Cart) -> tuple[CartState, list[CatalogProduct]]:
    products = _cart_products(db, cart.id)
    state = evaluate_cart(cart.mode, products, adjuster_for(request, cart), cart.threshold_amount)
    return state, products


def _card_kwargs(
    cart: Cart, state: CartState, n_members: int, alert_types: list[str]
) -> dict[str, object]:
    return {
        "id": cart.id,
        "name": cart.name,
        "mode": cart.mode,
        "scraper_id": cart.scraper_id,
        "currency": state.currency,
        "member_count": n_members,
        "active_count": state.active_count,
        "excluded_count": state.excluded_count,
        "has_delisted": state.has_delisted,
        "any_on_sale": state.any_on_sale,
        "all_on_sale": state.all_on_sale,
        "total_full": state.total_full,
        "total_discounted": state.total_discounted,
        "adjustments": [_to_adjustment(a) for a in state.adjustments],
        "final_price": state.final_price,
        "threshold_amount": cart.threshold_amount,
        "threshold": _to_threshold(state),
        "alert_types": alert_types,
        "created_at": cart.created_at,
    }


def _card(db: SessionDep, request: Request, cart: Cart) -> CartCard:
    state, products = _state(db, request, cart)
    kwargs = _card_kwargs(cart, state, len(products), _alert_types(db, cart.id))
    return CartCard(**kwargs)  # type: ignore[arg-type]


def _detail(db: SessionDep, request: Request, cart: Cart) -> CartDetail:
    state, products = _state(db, request, cart)
    members = [_member_out(p, p.is_available and not p.removed) for p in products]
    kwargs = _card_kwargs(cart, state, len(products), _alert_types(db, cart.id))
    return CartDetail(**kwargs, members=members)  # type: ignore[arg-type]


@router.get("", response_model=list[CartCard], summary="List the current user's carts (cards).")
def list_carts(user: UserDep, db: SessionDep, request: Request) -> list[CartCard]:
    carts = db.scalars(
        select(Cart)
        .where(Cart.user_id == user.sub)
        .order_by(Cart.created_at.desc(), Cart.id.desc())
    ).all()
    return [_card(db, request, c) for c in carts]


@router.post("", response_model=CartDetail, status_code=201, summary="Create a cart (mode fixed).")
def create_cart(body: CartCreate, user: UserDep, db: SessionDep, request: Request) -> CartDetail:
    if body.mode == "scraper_specific":
        if not body.scraper_id:
            raise APIError(
                422, "scraper_id_required", "scraper_specific carts require a scraper_id"
            )
        if body.scraper_id not in loaded_scrapers(request):
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
    return _detail(db, request, cart)


@router.get("/{cart_id}", response_model=CartDetail, summary="Get one cart with its members.")
def get_cart(cart_id: int, user: UserDep, db: SessionDep, request: Request) -> CartDetail:
    return _detail(db, request, _get_owned(db, user, cart_id))


@router.patch("/{cart_id}", response_model=CartDetail, summary="Rename a cart (mode immutable).")
def patch_cart(
    cart_id: int, body: CartPatch, user: UserDep, db: SessionDep, request: Request
) -> CartDetail:
    cart = _get_owned(db, user, cart_id)
    fields = body.model_fields_set
    if body.name is not None:
        cart.name = body.name
    if "threshold_amount" in fields:  # present (even as null) → set or clear
        if body.threshold_amount is None:
            cart.threshold_amount = None
        elif body.threshold_amount <= 0:
            raise APIError(422, "threshold_must_be_positive", "threshold_amount must be > 0")
        else:
            cart.threshold_amount = body.threshold_amount
    db.commit()
    db.refresh(cart)
    return _detail(db, request, cart)


@router.delete("/{cart_id}", status_code=204, summary="Delete a cart (only the cart, CART-R3).")
def delete_cart(cart_id: int, user: UserDep, db: SessionDep) -> None:
    cart = _get_owned(db, user, cart_id)
    db.delete(cart)  # cart_members cascade; catalog products are untouched
    db.commit()


@router.post(
    "/{cart_id}/items", response_model=CartDetail, summary="Add products to a cart (5.B2)."
)
def add_items(
    cart_id: int, body: CartItemsBody, user: UserDep, db: SessionDep, request: Request
) -> CartDetail:
    cart = _get_owned(db, user, cart_id)
    ids = list(dict.fromkeys(body.product_ids))  # dedupe, preserve order

    products = db.scalars(
        select(CatalogProduct).where(CatalogProduct.user_id == user.sub, CatalogProduct.id.in_(ids))
    ).all()
    by_id = {p.id: p for p in products}
    missing = [i for i in ids if i not in by_id]
    if missing:
        raise APIError(422, "product_not_found", f"not in your catalog: {missing}")

    ordered = [by_id[i] for i in ids]

    delisted = [p.id for p in ordered if p.removed]
    if delisted:
        raise APIError(422, "product_delisted", f"delisted products cannot be added: {delisted}")

    if cart.mode == "scraper_specific":
        wrong = [p.id for p in ordered if p.plugin_id != cart.scraper_id]
        if wrong:
            raise APIError(422, "product_scraper_mismatch", f"not from {cart.scraper_id}: {wrong}")

    existing_currencies = {p.currency for p in _cart_products(db, cart.id)}
    currencies = existing_currencies | {p.currency for p in ordered}
    if len(currencies) > 1:
        raise APIError(422, "currency_mismatch", f"a cart holds one currency: {sorted(currencies)}")

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
    return _detail(db, request, cart)


@router.delete(
    "/{cart_id}/items", response_model=CartDetail, summary="Remove cart members (no-op if absent)."
)
def remove_items(
    cart_id: int, body: CartItemsBody, user: UserDep, db: SessionDep, request: Request
) -> CartDetail:
    cart = _get_owned(db, user, cart_id)
    members = db.scalars(
        select(CartMember).where(
            CartMember.cart_id == cart.id, CartMember.product_id.in_(body.product_ids)
        )
    ).all()
    for m in members:  # absent ids are a no-op
        db.delete(m)
    db.commit()
    return _detail(db, request, cart)


@router.put(
    "/{cart_id}/alert-types",
    response_model=CartDetail,
    summary="Set the alert types enabled on a cart (6.B1).",
)
def set_alert_types(
    cart_id: int, body: CartAlertTypesBody, user: UserDep, db: SessionDep, request: Request
) -> CartDetail:
    """Replace the cart's enabled alert types with the full set in the body (presence =
    enabled). Unknown types are rejected as a batch. Enabling the first type seeds the
    per-cart baseline and clearing them all deletes it (6.B2/6.B3)."""
    cart = _get_owned(db, user, cart_id)

    valid = {t.value for t in AlertType}
    desired = list(dict.fromkeys(body.alert_types))  # dedupe, preserve order
    unknown = [t for t in desired if t not in valid]
    if unknown:
        raise APIError(422, "unknown_alert_type", f"unknown alert type(s): {unknown}")

    current = set(
        db.scalars(select(CartAlertType.alert_type).where(CartAlertType.cart_id == cart.id)).all()
    )
    target = set(desired)
    for row in db.scalars(
        select(CartAlertType).where(CartAlertType.cart_id == cart.id)
    ):  # remove no-longer-wanted rows
        if row.alert_type not in target:
            db.delete(row)
    for t in desired:  # add newly-enabled rows (presence = enabled)
        if t not in current:
            db.add(CartAlertType(cart_id=cart.id, alert_type=t))
    db.commit()

    # Baseline lifecycle (6.B2/6.B3): seed on the first type enabled — from the cart's
    # current state, so the first run has a reference and stays silent (ALERT-R8) — and
    # delete it once the last type is disabled. (Cadence off/on re-seeding is 6.B7.)
    if target:
        if not current:  # 0 → ≥1 types: seed the baseline
            state, products = _state(db, request, cart)
            upsert_snapshot(db, user.sub, cart.id, snapshot_payload(products, state))
            db.commit()
    else:  # ≥0 → 0 types: drop the baseline
        delete_snapshot(db, user.sub, cart.id)
        db.commit()
    return _detail(db, request, cart)
