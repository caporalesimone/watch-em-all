"""Unit tests for the Catalog Update Service (catalog-update-service.md).

Pure service-level tests: an in-memory SQLite session, the service called
directly with explicit (user_id, plugin_id, products). No app, no HTTP. SQLite
does not enforce FKs by default, so a bare user_id needs no users row here.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.core.catalog import update_catalog, upsert_products
from src.core.contracts import Product
from src.core.models import CatalogProduct, PriceHistory

PLUGIN = "dragon_store"
USER = 1


@pytest.fixture()
def session() -> Iterator[Session]:
    from src.core.db import create_schema, init_engine, new_session

    init_engine("sqlite+pysqlite:///:memory:")
    create_schema()
    s = new_session()
    try:
        yield s
    finally:
        s.close()


def _product(**over: object) -> Product:
    base: dict[str, object] = {
        "plugin_id": PLUGIN,
        "external_id": "abc123",
        "url": "https://example.com/p.1.1.1.gp.35880.uw",
        "name": "Necronomicon",
        "image_url": None,
        "price_current": Decimal("40.00"),
        "price_original": Decimal("50.00"),
        "discount_pct": None,
        "currency": "EUR",
        "is_available": True,
        "scraped_at": datetime.now(UTC),
        "extra": {},
    }
    base.update(over)
    return Product(**base)  # type: ignore[arg-type]


def _count(session: Session, model: type) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_new_product_then_idempotent(session: Session) -> None:
    first = update_catalog(session, USER, PLUGIN, [_product()])
    assert (first.found, first.new, first.price_changes, first.removed) == (1, 1, 1, 0)
    assert _count(session, CatalogProduct) == 1
    assert _count(session, PriceHistory) == 1

    # Same delivery again: zero new products, zero history entries (CATSVC-R4).
    second = update_catalog(session, USER, PLUGIN, [_product()])
    assert (second.found, second.new, second.price_changes, second.removed) == (1, 0, 0, 0)
    assert _count(session, CatalogProduct) == 1
    assert _count(session, PriceHistory) == 1


def _seconds_apart(stored: datetime, expected: datetime) -> float:
    """SQLite hands back naive datetimes; treat them as the UTC they were written as."""
    aware = stored if stored.tzinfo is not None else stored.replace(tzinfo=UTC)
    return abs((aware - expected).total_seconds())


def test_last_seen_follows_the_scrape_not_the_clock(session: Session) -> None:
    """``last_seen_at`` is the scraper's observation time. A delivery rebuilt from a cached
    response carries an older ``scraped_at``, and the row must show *that* — otherwise the
    one field meant to say how fresh the data is reports when we last replayed it."""
    observed = datetime.now(UTC) - timedelta(hours=6)
    update_catalog(session, USER, PLUGIN, [_product(scraped_at=observed)])
    row = session.scalar(select(CatalogProduct))
    assert row is not None
    assert _seconds_apart(row.last_seen_at, observed) < 1

    # A later run served from the same cache entry does not move it forward.
    update_catalog(session, USER, PLUGIN, [_product(scraped_at=observed)])
    session.refresh(row)
    assert _seconds_apart(row.last_seen_at, observed) < 1

    # A real fetch does.
    fresh = datetime.now(UTC)
    update_catalog(session, USER, PLUGIN, [_product(scraped_at=fresh)])
    session.refresh(row)
    assert _seconds_apart(row.last_seen_at, fresh) < 1


def test_price_change_appends_history(session: Session) -> None:
    update_catalog(session, USER, PLUGIN, [_product(price_current=Decimal("40.00"))])
    delta = update_catalog(session, USER, PLUGIN, [_product(price_current=Decimal("35.00"))])
    assert delta.price_changes == 1
    assert _count(session, PriceHistory) == 2
    row = session.scalar(select(CatalogProduct))
    assert row is not None
    assert row.price_current == Decimal("35.00")


def test_availability_change_appends_history(session: Session) -> None:
    update_catalog(session, USER, PLUGIN, [_product(is_available=True)])
    # Same price, only availability flips -> still a history entry (CATSVC-R4).
    delta = update_catalog(session, USER, PLUGIN, [_product(is_available=False)])
    assert delta.price_changes == 1
    assert _count(session, PriceHistory) == 2


def test_discount_computed_when_missing(session: Session) -> None:
    update_catalog(
        session,
        USER,
        PLUGIN,
        [_product(price_original=Decimal("50.00"), price_current=Decimal("40.00"))],
    )
    row = session.scalar(select(CatalogProduct))
    assert row is not None
    assert row.discount_pct == Decimal("20.00")  # (50-40)/50*100


def test_missing_original_resolves_from_history(session: Session) -> None:
    # First run knows the list price; full price, no discount.
    update_catalog(
        session,
        USER,
        PLUGIN,
        [_product(price_original=Decimal("50.00"), price_current=Decimal("50.00"))],
    )
    # Second run: scraper omits the list price -> resolved from history (50).
    update_catalog(
        session,
        USER,
        PLUGIN,
        [_product(price_original=None, price_current=Decimal("40.00"))],
    )
    row = session.scalar(select(CatalogProduct))
    assert row is not None
    assert row.price_original == Decimal("50.00")
    assert row.discount_pct == Decimal("20.00")


def test_delisting_then_reappear(session: Session) -> None:
    update_catalog(session, USER, PLUGIN, [_product()])

    # Empty delivery: the plugin's rows not seen are delisted (no history entry).
    gone = update_catalog(session, USER, PLUGIN, [])
    assert gone.removed == 1
    assert _count(session, PriceHistory) == 1  # delisting is not a price event
    row = session.scalar(select(CatalogProduct))
    assert row is not None and row.removed is True

    # Reappears: removed flips back, not counted as new (CATSVC-R5).
    back = update_catalog(session, USER, PLUGIN, [_product()])
    assert back.new == 0
    row = session.scalar(select(CatalogProduct))
    assert row is not None and row.removed is False


def test_duplicate_external_id_in_one_delivery_no_duplicate_row(session: Session) -> None:
    update_catalog(session, USER, PLUGIN, [_product(), _product()])
    assert _count(session, CatalogProduct) == 1


def test_other_plugin_rows_not_delisted(session: Session) -> None:
    update_catalog(session, USER, PLUGIN, [_product(external_id="a")])
    update_catalog(
        session, USER, "other_plugin", [_product(plugin_id="other_plugin", external_id="b")]
    )
    # A delivery for PLUGIN must not delist other_plugin's rows.
    update_catalog(session, USER, PLUGIN, [_product(external_id="a")])
    other = session.scalar(select(CatalogProduct).where(CatalogProduct.plugin_id == "other_plugin"))
    assert other is not None and other.removed is False


# --- CATSVC-R2b: the non-delisting write path ---


def test_upsert_products_never_delists(session: Session) -> None:
    """A partial or failed delivery must leave untouched rows alone. This is the guard
    against the failure that used to wipe a user's catalogue whenever a site went dark."""
    update_catalog(session, USER, PLUGIN, [_product(external_id="keep")])

    # An empty delivery through the non-delisting path says "we learned nothing".
    counters = upsert_products(session, USER, [])

    assert counters.removed == 0
    row = session.scalar(select(CatalogProduct).where(CatalogProduct.external_id == "keep"))
    assert row is not None
    assert row.removed is False


def test_empty_delivery_through_update_catalog_still_delists(session: Session) -> None:
    """The complementary contract: a *complete* delivery that offers nothing does delist —
    that behaviour is deliberate and must not regress with the guard in place."""
    update_catalog(session, USER, PLUGIN, [_product(external_id="gone")])

    counters = update_catalog(session, USER, PLUGIN, [])

    assert counters.removed == 1
    row = session.scalar(select(CatalogProduct).where(CatalogProduct.external_id == "gone"))
    assert row is not None
    assert row.removed is True


def test_upsert_products_inserts_and_updates_like_a_full_delivery(session: Session) -> None:
    inserted = upsert_products(session, USER, [_product(external_id="p1")])
    assert (inserted.new, inserted.found) == (1, 1)

    updated = upsert_products(
        session, USER, [_product(external_id="p1", price_current=Decimal("30.00"))]
    )
    assert updated.new == 0
    row = session.scalar(select(CatalogProduct).where(CatalogProduct.external_id == "p1"))
    assert row is not None
    assert row.price_current == Decimal("30.00")
    # A price move is still a history event on this path (CATSVC-R4).
    assert session.scalar(select(func.count()).select_from(PriceHistory)) == 2


def test_delisting_records_when_and_relisting_forgets_it(session: Session) -> None:
    """9.B6: `removed` alone cannot answer "delisted since when" — which the catalog cleanups
    sort on, and which a delisting notification needs in order to fire once instead of on every
    run. And when a product comes back the date has to go, or it outlives the fact it records."""
    product = _product()
    update_catalog(session, USER, PLUGIN, [product])
    row = session.scalars(select(CatalogProduct)).one()
    assert row.removed_at is None

    update_catalog(session, USER, PLUGIN, [])  # a complete delivery that no longer offers it
    session.refresh(row)
    assert row.removed is True
    assert row.removed_at is not None

    update_catalog(session, USER, PLUGIN, [product])  # back on the site
    session.refresh(row)
    assert row.removed is False
    assert row.removed_at is None


# --- per-product statistics (9.B6b) -----------------------------------------------------


def test_a_first_sighting_starts_the_counters_without_inventing_a_change(
    session: Session,
) -> None:
    update_catalog(session, USER, PLUGIN, [_product(price_current=Decimal("40.00"))])
    row = session.scalars(select(CatalogProduct)).one()

    assert row.observations == 1
    assert row.cache_hits == 0
    # Not a price change: there was nothing to change from, and counting it would add one to
    # every product's volatility for ever.
    assert row.price_changes == 0
    assert row.availability_changes == 0
    assert row.price_min == row.price_max == Decimal("40.00")
    assert row.last_price_change_at is not None


def test_a_fresh_read_counts_as_an_observation_and_a_replay_does_not(session: Session) -> None:
    """The distinction 9.X4 established, as a counter: a delivery served from the scrape cache
    carries the timestamp of the fetch that filled it, so an unchanged timestamp means we are
    being handed the same page again. Counting that as an observation would make the number
    mean "how many times we re-processed this", which says nothing about the product."""
    first = datetime.now(UTC) - timedelta(hours=2)
    update_catalog(session, USER, PLUGIN, [_product(scraped_at=first)])
    row = session.scalars(select(CatalogProduct)).one()

    update_catalog(session, USER, PLUGIN, [_product(scraped_at=first)])  # cache replay
    session.refresh(row)
    assert (row.observations, row.cache_hits) == (1, 1)

    update_catalog(session, USER, PLUGIN, [_product(scraped_at=datetime.now(UTC))])
    session.refresh(row)
    assert (row.observations, row.cache_hits) == (2, 1)


def test_price_and_availability_changes_are_counted_apart(session: Session) -> None:
    """The run-level counter called price_changes increments on availability moves too, and on
    the first history row: it counts history rows written. These two do not."""
    update_catalog(session, USER, PLUGIN, [_product(price_current=Decimal("40.00"))])
    row = session.scalars(select(CatalogProduct)).one()

    update_catalog(session, USER, PLUGIN, [_product(price_current=Decimal("30.00"))])
    session.refresh(row)
    assert (row.price_changes, row.availability_changes) == (1, 0)

    update_catalog(
        session, USER, PLUGIN, [_product(price_current=Decimal("30.00"), is_available=False)]
    )
    session.refresh(row)
    assert (row.price_changes, row.availability_changes) == (1, 1)


def test_the_range_remembers_the_best_and_worst_price_seen(session: Session) -> None:
    for price in ("40.00", "24.90", "44.00", "39.99"):
        update_catalog(
            session,
            USER,
            PLUGIN,
            [_product(price_current=Decimal(price), scraped_at=datetime.now(UTC))],
        )
    row = session.scalars(select(CatalogProduct)).one()

    assert row.price_min == Decimal("24.90")
    assert row.price_max == Decimal("44.00")
    assert row.price_min_at is not None and row.price_max_at is not None
    # And "how long has this price held" moved with the last actual change.
    assert row.last_price_change_at is not None
