"""Integration tests for the alert run (phase 6.B6): run_for_user over a real session.

Exercises the full loop: silent seed on the first run, one aggregated digest per user
across multiple carts, and no repeat when nothing changed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from src.core.alert_engine import run_for_user
from src.core.db import Base
from src.core.models import Cart, CartAlertType, CartMember, CatalogProduct, User

NOW = datetime(2026, 7, 22, 9, 0, tzinfo=UTC)


def _session() -> Session:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return Session(engine)


def _product(db: Session, user_id: int, ext: str, *, price: str, discount: str) -> CatalogProduct:
    p = CatalogProduct(
        user_id=user_id,
        plugin_id="tp_scraper",
        external_id=ext,
        url=f"https://x/{ext}",
        name=f"Item {ext}",
        price_current=Decimal(price),
        price_original=Decimal("100.00"),
        discount_pct=Decimal(discount),
        is_available=True,
    )
    db.add(p)
    db.flush()
    return p


def _cart_with_product(
    db: Session,
    user_id: int,
    name: str,
    product: CatalogProduct,
    *,
    alert_types: tuple[str, ...] = ("PRODUCT_ON_SALE",),
) -> Cart:
    cart = Cart(user_id=user_id, name=name, mode="cross")
    db.add(cart)
    db.flush()
    db.add(CartMember(cart_id=cart.id, product_id=product.id))
    for t in alert_types:
        db.add(CartAlertType(cart_id=cart.id, alert_type=t))
    db.flush()
    return cart


def _no_adjuster(_cart: Cart) -> None:
    return None


def test_run_seeds_then_one_digest_then_no_repeat() -> None:
    with _session() as db:
        user = User(username="alice@example.com", password_hash="x")
        db.add(user)
        db.flush()
        p1 = _product(db, user.id, "a", price="100.00", discount="0")
        p2 = _product(db, user.id, "b", price="100.00", discount="0")
        _cart_with_product(db, user.id, "Cart A", p1)
        _cart_with_product(db, user.id, "Cart B", p2)
        db.commit()

        # First run: baselines are seeded silently, nothing to notify.
        assert run_for_user(db, user.id, _no_adjuster, now=NOW) is None

        # Both products go on sale.
        p1.discount_pct, p1.price_current = Decimal("20"), Decimal("80.00")
        p2.discount_pct, p2.price_current = Decimal("15"), Decimal("85.00")
        db.commit()

        # One aggregated digest for the user, covering BOTH carts (AEV-R1).
        log = run_for_user(db, user.id, _no_adjuster, now=NOW)
        assert log is not None
        assert log.kind == "alert_digest"
        payload = log.payload_json
        assert payload["user_id"] == user.id
        assert len(payload["cart_alerts"]) == 2
        names = {c["cart_name"] for c in payload["cart_alerts"]}
        assert names == {"Cart A", "Cart B"}
        for c in payload["cart_alerts"]:
            assert c["products"][0]["tags"] == ["PRODUCT_ON_SALE"]
            assert c["products"][0]["price_previous"] == "100.00"  # Decimal → string (DB-R3)

        # Nothing changed since → no new notification (baseline already advanced).
        assert run_for_user(db, user.id, _no_adjuster, now=NOW) is None


def test_only_changed_carts_appear_in_digest() -> None:
    with _session() as db:
        user = User(username="bob@example.com", password_hash="x")
        db.add(user)
        db.flush()
        p1 = _product(db, user.id, "a", price="100.00", discount="0")
        p2 = _product(db, user.id, "b", price="100.00", discount="0")
        _cart_with_product(db, user.id, "Changes", p1)
        _cart_with_product(db, user.id, "Steady", p2)
        db.commit()

        run_for_user(db, user.id, _no_adjuster, now=NOW)  # seed
        p1.discount_pct, p1.price_current = Decimal("20"), Decimal("80.00")  # only cart 1 changes
        db.commit()

        log = run_for_user(db, user.id, _no_adjuster, now=NOW)
        assert log is not None
        assert [c["cart_name"] for c in log.payload_json["cart_alerts"]] == ["Changes"]


def test_delisting_notifies_once_through_the_whole_run() -> None:
    # 9.B9 end to end: the run that observes the delisting notifies, the next one does not,
    # and a price move on the delisted row stays silent (ALERT-R12).
    with _session() as db:
        user = User(username="carol@example.com", password_hash="x")
        db.add(user)
        db.flush()
        p = _product(db, user.id, "a", price="100.00", discount="0")
        _cart_with_product(
            db, user.id, "Gone", p, alert_types=("PRODUCT_ON_SALE", "PRODUCT_DELISTED")
        )
        db.commit()

        assert run_for_user(db, user.id, _no_adjuster, now=NOW) is None  # seed

        p.removed = True
        db.commit()
        log = run_for_user(db, user.id, _no_adjuster, now=NOW)
        assert log is not None
        (cart,) = log.payload_json["cart_alerts"]
        assert cart["products"][0]["tags"] == ["PRODUCT_DELISTED"]
        assert cart["products"][0]["price_previous"] == "100.00"

        # Still delisted, and now cheaper on paper: no second event.
        p.discount_pct, p.price_current = Decimal("20"), Decimal("80.00")
        db.commit()
        assert run_for_user(db, user.id, _no_adjuster, now=NOW) is None
