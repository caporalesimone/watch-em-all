"""The scraper base's product assembler (base.py ``build_product``, SCR-R18). C8.

This is the conformance test for the parts of the Product contract that are the same for every
scraper. It exists because those parts were written by hand in three places across two plugins
and had already drifted: a discarded ``fetched_at`` (C3), and two different predicates for
filtering ``extra``. A rule that lives in one place and is asserted here cannot drift again.

No site and no database: the assembler is pure.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from src.core.plugins.base import PREORDER_TAG, ScraperPlugin
from src.core.plugins.context import PluginContext


class _Scraper(ScraperPlugin):
    """The smallest possible scraper: an identity seed and nothing else."""

    plugin_id = "probe"

    def identity_seed(self, raw: Any) -> str | None:
        return f"seed:{raw}"


def _context(logger: logging.Logger | None = None) -> PluginContext:
    return PluginContext(
        engine=None,  # type: ignore[arg-type]
        db=None,  # type: ignore[arg-type]
        logger=logger or logging.getLogger("test.probe"),
        config={},
        update_catalog=lambda user_id, products: None,  # type: ignore[arg-type,return-value]
    )


def _build(**over: Any) -> Any:
    base: dict[str, Any] = {
        "raw": "35880",
        "url": "https://example.com/p.gp.35880.uw",
        "name": "Necronomicon",
        "price_current": Decimal("40.00"),
    }
    base.update(over)
    return _Scraper().build_product(_context(), **base)


def test_identity_always_comes_from_the_template_method() -> None:
    """A hand-filled external_id breaks the history silently, so the plugin cannot pass one."""
    product = _build()

    assert product.external_id == _Scraper()._stable_id("seed:35880")
    assert product.plugin_id == "probe"


def test_discount_is_never_computed_by_the_scraper() -> None:
    """CATSVC-R3: the core derives it from original/current. A plugin computing its own answers
    a different question — 9.X10 found exactly that printed as a percentage."""
    product = _build(price_original=Decimal("50.00"))

    assert product.discount_pct is None


def test_scraped_at_is_when_the_site_answered() -> None:
    """PROD-R8. The clock is the fallback, not the default: a page replayed from the scrape
    cache is old data, and stamping it "now" makes it look fresh."""
    answered = datetime.now(UTC) - timedelta(hours=6)

    assert _build(fetched_at=answered).scraped_at == answered
    assert (datetime.now(UTC) - _build().scraped_at).total_seconds() < 5


def test_extra_drops_none_and_only_none() -> None:
    """The two Dragon Store copies had drifted to different predicates, so an empty description
    survived from a detail page and was discarded from a listing card. Nobody decided that."""
    product = _build(extra={"sku": "35880", "description": "", "missing": None, "zero": 0})

    assert product.extra == {"sku": "35880", "description": "", "zero": 0}


def test_availability_is_read_as_schema_org() -> None:
    assert _build(availability="InStock").is_available is True
    assert _build(availability="OutOfStock").is_available is False
    # PreOrder is orderable today, and says so with a tag of its own.
    preorder = _build(availability="PreOrder")
    assert preorder.is_available is True
    assert PREORDER_TAG in preorder.tags
    # No availability at all is not "available": a scraper that cannot tell must not claim it.
    assert _build().is_available is False


def test_an_unknown_availability_token_is_logged_not_guessed(
    caplog: Any,
) -> None:
    """A vocabulary the site invented is a change we need to see in the log, not a silent
    `False` that reads as "out of stock" for as long as nobody looks."""
    with caplog.at_level(logging.WARNING):
        product = _build(availability="BackOrder")

    assert product.is_available is False
    assert "unknown availability" in caplog.text
    assert "BackOrder" in caplog.text


def test_the_breadcrumb_becomes_a_category_path() -> None:
    product = _build(breadcrumb=[("Giochi", "https://x/g"), ("GDR", None)])

    assert [(c.text, c.link) for c in product.category] == [
        ("Giochi", "https://x/g"),
        ("GDR", None),
    ]


def test_tags_the_plugin_accumulated_survive() -> None:
    """The site's own labels are site knowledge, so they arrive already accumulated — and the
    "Free" tag a price resolution added must not be lost by the assembler."""
    scraper = _Scraper()
    tags = scraper.new_tags()
    tags.add_tag("Free")

    product = scraper.build_product(
        _context(),
        raw="1",
        url="https://example.com/x",
        name="Digital download",
        price_current=Decimal("0.00"),
        availability="PreOrder",
        tags=tags,
    )

    assert set(product.tags) == {"Free", PREORDER_TAG}


def test_a_brand_without_a_name_is_no_brand() -> None:
    assert _build(brand_link="https://x/b").brand is None
    branded = _build(brand_text="Raven", brand_link="https://x/b")
    assert branded.brand is not None
    assert (branded.brand.text, branded.brand.link) == ("Raven", "https://x/b")
