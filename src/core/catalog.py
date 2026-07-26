"""Catalog Update Service (catalog-update-service.md).

The single place where scraper output becomes persistent state: it takes a
user's current list of products, computes the deltas and writes only the
changes. The scraper is stateless — history, availability and delisting are all
decided here (CATSVC-R1).

The public entry point is :func:`update_catalog`. In phase 3 it is exercised
directly in tests; from phase-3 PR2 the Plugin Context binds ``session`` and the
calling plugin's ``plugin_id`` and exposes ``update_catalog(user_id, products)``
to the plugin.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.contracts import DeltaCounters, Product
from src.core.models import CatalogProduct, PriceHistory


def _last_history_entry(session: Session, product_id: int) -> PriceHistory | None:
    """The most recent history entry for a product. Append-only with a
    monotonic id, so the max id is the latest — robust even when several
    entries share a coarse ``recorded_at`` (e.g. SQLite's 1-second clock)."""
    return session.scalar(
        select(PriceHistory)
        .where(PriceHistory.product_id == product_id)
        .order_by(PriceHistory.id.desc())
        .limit(1)
    )


def _resolve_prices(p: Product, last: PriceHistory | None) -> tuple[Decimal, Decimal]:
    """Resolve the price fields the scraper may have left as None (CATSVC-R3,
    normative); returns ``(price_original, discount_pct)`` as concrete Decimals.

    ``price_original`` ("list") defaults to the last known list price, or the
    current price if there is no history. ``discount_pct`` is derived from the
    two; full price (or above the known list) yields 0.
    """
    if p.price_original is not None:
        original = p.price_original
    elif last is not None:
        original = last.price_original
    else:
        original = p.price_current

    if p.discount_pct is not None:
        discount = p.discount_pct
    elif original > p.price_current:
        discount = round((original - p.price_current) / original * Decimal(100), 2)
    else:
        discount = Decimal(0)
    return original, discount


def _insert_product(
    session: Session, user_id: int, p: Product, original: Decimal, discount: Decimal
) -> CatalogProduct:
    row = CatalogProduct(
        user_id=user_id,
        plugin_id=p.plugin_id,
        external_id=p.external_id,
        url=p.url,
        name=p.name,
        image_url=p.image_url,
        brand_text=p.brand.text if p.brand else None,
        brand_link=p.brand.link if p.brand else None,
        tags=list(p.tags),
        category=[c.model_dump() for c in p.category],
        extra_json=p.extra,
        currency=p.currency,
        price_current=p.price_current,
        price_original=original,
        discount_pct=discount,
        is_available=p.is_available,
        removed=False,
    )
    session.add(row)
    session.flush()  # assign row.id and make it visible to later finds in this delivery
    return row


def _update_mutable_fields(
    row: CatalogProduct, p: Product, original: Decimal, discount: Decimal
) -> None:
    """Refresh everything that can change (CATSVC-R5); a delisted product that
    reappears goes back to removed=False."""
    row.name = p.name
    row.url = p.url
    row.image_url = p.image_url
    row.brand_text = p.brand.text if p.brand else None
    row.brand_link = p.brand.link if p.brand else None
    row.tags = list(p.tags)
    row.category = [c.model_dump() for c in p.category]
    row.extra_json = p.extra
    row.currency = p.currency
    row.price_current = p.price_current
    row.price_original = original
    row.discount_pct = discount
    row.is_available = p.is_available
    row.removed = False
    row.last_seen_at = datetime.now(UTC)


def _append_history(
    session: Session, row: CatalogProduct, p: Product, original: Decimal, discount: Decimal
) -> None:
    session.add(
        PriceHistory(
            product_id=row.id,
            user_id=row.user_id,
            price_current=p.price_current,
            price_original=original,
            discount_pct=discount,
            is_available=p.is_available,
        )
    )


def _apply_delivery(
    session: Session, user_id: int, products: list[Product]
) -> tuple[DeltaCounters, set[int]]:
    """Insert/refresh every delivered product (and its history entry when the price or
    availability moved). Returns the counters and the touched row ids — the caller decides
    whether the absence of a row means "delisted" or "we simply were not told". No commit."""
    counters = DeltaCounters(found=len(products))
    seen: set[int] = set()

    for p in products:
        row = session.scalar(
            select(CatalogProduct).where(
                CatalogProduct.user_id == user_id,
                CatalogProduct.plugin_id == p.plugin_id,
                CatalogProduct.external_id == p.external_id,
            )
        )
        last = _last_history_entry(session, row.id) if row is not None else None
        original, discount = _resolve_prices(p, last)

        if row is None:
            row = _insert_product(session, user_id, p, original, discount)
            counters.new += 1
        else:
            _update_mutable_fields(row, p, original, discount)

        # CATSVC-R4: a history entry only on a price OR availability change.
        if (
            last is None
            or last.price_current != p.price_current
            or last.is_available != p.is_available
        ):
            _append_history(session, row, p, original, discount)
            counters.price_changes += 1
        seen.add(row.id)

    return counters, seen


def upsert_products(session: Session, user_id: int, products: list[Product]) -> DeltaCounters:
    """Apply a delivery **without delisting anything**: CATSVC-R6 minus CATSVC-R2. Atomic.

    For deliveries that say nothing about the rest of the catalog, where the delisting
    sweep would be plain wrong:

    - a **partial** delivery — one product resolved as the user adds its watch;
    - a **failed** run — no products because we could not read the site. "We do not know"
      is not "they are gone": an anti-bot interstitial or an outage would otherwise wipe a
      user's whole catalog for that scraper, drag their carts to ``has_delisted`` and
      suppress their alerts (ALERT-R12) until the site came back.
    """
    counters, _seen = _apply_delivery(session, user_id, products)
    session.commit()
    return counters


def update_catalog(
    session: Session, user_id: int, plugin_id: str, products: list[Product]
) -> DeltaCounters:
    """Apply a scraper's **complete** delivery to the user's catalog and return the delta
    counters (CATSVC-R6), delisting whatever the site no longer offers (CATSVC-R2).

    ``plugin_id`` is explicit (not read from the products) so an empty delivery still
    delists that plugin's rows — which is right when the site answered and offered
    nothing, and wrong when we never managed to ask. Callers that cannot tell the
    difference apart must use :func:`upsert_products`. Atomic: commits its own unit of work.
    """
    counters, seen = _apply_delivery(session, user_id, products)

    # Delisting (CATSVC-R2): this plugin's rows not seen in this delivery. No
    # history entry — delisting is not a price event.
    rows = session.scalars(
        select(CatalogProduct).where(
            CatalogProduct.user_id == user_id,
            CatalogProduct.plugin_id == plugin_id,
        )
    ).all()
    for row in rows:
        if row.id not in seen and not row.removed:
            row.removed = True
            counters.removed += 1

    session.commit()
    return counters
