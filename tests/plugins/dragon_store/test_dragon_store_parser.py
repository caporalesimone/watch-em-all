"""Parser + sanitiser tests for Dragon Store, on the real saved fixtures (3.B6/3.B7).

The fixtures are byte-exact captures (windows-1252, embedded HTML entities); the
parser must read the JSON-LD Product, take ``price_original`` from the DOM "P.
Listino" row, ignore the 20-46 related products, and decode the encoding right.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from src.plugins.scrapers.dragon_store.backend.parser import (
    DragonStoreChallenge,
    DragonStoreParseError,
    DragonStoreRateLimited,
    DragonStoreSoftError,
    classify_url,
    page_url,
    parse_category,
    parse_product,
)
from src.plugins.scrapers.dragon_store.backend.sanitizer import (
    load_title_labels,
    sanitize_title,
)

_FIX = Path(__file__).parent / "fixtures"


def _read(name: str) -> bytes:
    return (_FIX / name).read_bytes()


def test_parse_discounted() -> None:
    p = parse_product(_read("gp_896_discounted.html"), "https://www.dragonstore.it/x.gp.896.uw")
    assert p.price_current == Decimal("9.90")
    assert p.price_original == Decimal("24.90")  # discounted: listino > current
    assert p.currency == "EUR"
    assert p.availability == "InStock"
    assert p.brand_text == "Giochi Uniti"
    assert p.brand_link == "https://www.dragonstore.it/giochi-uniti.1.0.0.br.86.uw"
    assert p.sku == "SL1300"
    assert "OFFERTA RAVEN PRIME" in p.name  # parser does NOT sanitise (the plugin does)
    assert "Cthulhu '90" in p.name  # JSON-LD '"90' apostrophe artifact recovered
    assert '"' not in p.name
    assert p.image_url is not None and p.image_url.endswith(".jpg")


def test_parse_preorder() -> None:
    p = parse_product(_read("gp_36099_preorder.html"), "https://www.dragonstore.it/x.gp.36099.uw")
    assert p.availability == "PreOrder"
    assert p.price_current == Decimal("39.99")
    assert p.brand_text == "Raven Distribution"


def test_parse_out_of_stock_with_entity_in_name() -> None:
    p = parse_product(
        _read("gp_27006_out_of_stock.html"), "https://www.dragonstore.it/x.gp.27006.uw"
    )
    assert p.availability == "OutOfStock"
    assert "Città" in p.name  # JSON-LD "Citt&#224;" -> html.unescape -> "Città"


def test_parse_full_price_limited_edition() -> None:
    p = parse_product(
        _read("gp_34602_limited_edition.html"), "https://www.dragonstore.it/x.gp.34602.uw"
    )
    assert p.availability == "InStock"
    assert p.price_current == Decimal("89.99")
    assert p.price_original == Decimal("89.99")  # full price: listino == current
    assert "EDIZIONE LIMITATA" in p.name.upper()


def test_parse_other_category() -> None:
    p = parse_product(
        _read("gp_30708_other_category.html"), "https://www.dragonstore.it/x.gp.30708.uw"
    )
    assert p.availability == "InStock"
    assert p.price_current == Decimal("17.99")
    assert p.brand_text == "Winning Moves"
    assert p.brand_link == "https://www.dragonstore.it/winning-moves.1.0.0.br.204.uw"


def test_parse_breadcrumb_category() -> None:
    p = parse_product(_read("gp_896_discounted.html"), "https://www.dragonstore.it/x.gp.896.uw")
    names = [name for name, _url in p.breadcrumb]
    assert names == ["Giochi di Ruolo", "GDR Italiano", "Il Richiamo di Cthulhu"]
    # relative @id resolved to an absolute URL
    assert all(url and url.startswith("https://www.dragonstore.it/") for _n, url in p.breadcrumb)


def test_parse_raises_without_jsonld() -> None:
    with pytest.raises(DragonStoreParseError):
        parse_product(b"<html><body>no json-ld here</body></html>", "http://x/y.gp.1.uw")


def test_sanitize_removes_prefix_label() -> None:
    clean, found = sanitize_title(
        "OFFERTA RAVEN PRIME - Il Richiamo di Cthulhu", ["Offerta Raven Prime"]
    )
    assert clean == "Il Richiamo di Cthulhu"
    assert found == ["Offerta Raven Prime"]


def test_sanitize_keeps_internal_separators_when_no_label() -> None:
    clean, found = sanitize_title("Trivial Pursuit - Batman", ["Edizione Limitata"])
    assert clean == "Trivial Pursuit - Batman"
    assert found == []


def test_sanitize_limited_edition_keeps_rest_of_title() -> None:
    title = "EDIZIONE LIMITATA - Il Richiamo di Cthulhu - Cthulhu By Gaslight - Libro del Custode"
    clean, found = sanitize_title(title, ["Edizione Limitata"])
    assert found == ["Edizione Limitata"]
    assert clean == "Il Richiamo di Cthulhu - Cthulhu By Gaslight - Libro del Custode"


def test_load_title_labels_has_known_labels() -> None:
    labels = load_title_labels()
    assert "Offerta Raven Prime" in labels
    assert "Edizione Limitata" in labels


# --- non-product pages: the site serves gates and errors with HTTP 200 (2026-07-25) ---

_CHALLENGE = (
    b'<!DOCTYPE html><html lang="it"><head>'
    b"<title>Verifica accesso / Security Check</title></head>"
    b'<body><input type="checkbox" id="humanCheck"><script>'
    b'fetch("/ajaxRequests.asp?cmd=captcha_check_ok", '
    b"{headers: {'ReadyAjaxAuth': 'readypro'}})"
    b"</script></body></html>"
)

_SOFT_429 = (
    b'<div style="text-align:center;"><div id="pageNotFound" style="background:#eee;">'
    b"<p><strong>429</strong> <span>Too Many Requests</span>.</p></div></div>"
)

_SOFT_404 = (
    b'<div style="text-align:center;"><div id="pageNotFound">'
    b"<p><strong>404</strong> <span>Page Not Found</span>.</p></div></div>"
)


def test_interstitial_is_reported_as_a_challenge_not_a_parse_failure() -> None:
    with pytest.raises(DragonStoreChallenge):
        parse_product(_CHALLENGE, "https://www.dragonstore.it/x.gp.1.uw")


def test_soft_429_is_reported_as_rate_limiting() -> None:
    with pytest.raises(DragonStoreRateLimited) as excinfo:
        parse_product(_SOFT_429, "https://www.dragonstore.it/x.gp.1.uw")
    assert excinfo.value.status == 429


def test_other_soft_error_pages_carry_their_status() -> None:
    with pytest.raises(DragonStoreSoftError) as excinfo:
        parse_product(_SOFT_404, "https://www.dragonstore.it/x.gp.1.uw")
    assert excinfo.value.status == 404
    assert not isinstance(excinfo.value, DragonStoreRateLimited)


def test_every_non_product_page_stays_a_parse_error_for_old_callers() -> None:
    """The subclasses exist to be *reacted* to differently, not to escape existing
    handling: anything catching DragonStoreParseError must still catch them all."""
    for body in (_CHALLENGE, _SOFT_429, _SOFT_404, b"<html>nothing useful</html>"):
        with pytest.raises(DragonStoreParseError):
            parse_product(body, "https://www.dragonstore.it/x.gp.1.uw")


# --- URL classification (9.B1) ---------------------------------------------------------
#
# The two URLs below are the real ones behind the category fixtures; the relative forms are
# copied from the site's own markup (card links and breadcrumbs), which is what the category
# parser will feed this function from phase 9 on.

_CTHULHU = "https://www.dragonstore.it/il-richiamo-di-cthulhu.1.1.192.sp.uw?idA=19"
_CLASSICI = "https://www.dragonstore.it/classici-famiglia.1.1.115.sp.uw?idA=16"


@pytest.mark.parametrize(
    "url",
    [
        "https://www.dragonstore.it/x.1.19.192.gp.35880.uw",
        "https://www.dragonstore.it/x.1.19.192.gp.35880.uw?fd=1",
        "classici-famiglia-l-isola-proibita.1.16.115.gp.14415.uw",  # relative, from a card
        "WWW.DRAGONSTORE.IT/X.GP.1.UW",  # no scheme, shouting
    ],
)
def test_product_urls_are_recognised(url: str) -> None:
    assert classify_url(url) == "product"


@pytest.mark.parametrize(
    "url",
    [
        _CTHULHU,
        _CLASSICI,
        _CLASSICI + "&pg=2",  # a page of a paginated category is still the category
        "gdr-italiano.1.19.33.sp.uw",  # relative, from a breadcrumb
    ],
)
def test_category_urls_are_recognised(url: str) -> None:
    assert classify_url(url) == "category"


@pytest.mark.parametrize(
    "url",
    [
        "https://www.dragonstore.it/",
        "https://www.dragonstore.it/raven-distribution.1.0.0.br.18.uw",  # a brand page
        "giochi-di-ruolo.1.19.uw",  # department listing: sub-categories, no product cards
        "",
        "   ",
    ],
)
def test_everything_else_is_not_a_watchable_url(url: str) -> None:
    assert classify_url(url) is None


def test_the_host_is_deliberately_not_checked() -> None:
    """Shape alone decides. The site's own links are relative, so there is often no host
    to check, and every fixture-driven test reaches this plugin through a local mock
    server — pinning the hostname would refuse exactly that."""
    assert classify_url("http://127.0.0.1:8931/x.1.19.192.gp.35880.uw") == "product"
    assert classify_url("http://127.0.0.1:8931/x.1.1.192.sp.uw?idA=19") == "category"


def test_the_two_shapes_never_collide() -> None:
    """A category URL must not read as a product one, or adding a category would scrape a
    single page and silently deliver one product instead of the whole listing."""
    assert classify_url(_CTHULHU) != classify_url(
        "https://www.dragonstore.it/x.1.19.192.gp.35880.uw"
    )


# --- category listing (9.B2/9.B3) ------------------------------------------------------
#
# Against the pages actually fetched from the site on 2026-07-29: a single-page category that
# happens to hold every edge case (a preorder, a dented item, two products with no price), and
# pages 1 and 2 of a 21-page one.

_CTHULHU_URL = "https://www.dragonstore.it/il-richiamo-di-cthulhu.1.1.192.sp.uw?idA=19"
_CLASSICI_URL = "https://www.dragonstore.it/classici-famiglia.1.1.115.sp.uw?idA=16"


def test_category_cards_carry_everything_the_catalog_needs() -> None:
    page = parse_category(_read("sp_192_cthulhu_one_page.html"), _CTHULHU_URL)

    assert len(page.cards) == 39
    assert (page.total_items, page.page_size, page.total_pages) == (39, 50, 1)
    # The page's own breadcrumb stands in for the one a card does not carry; on this product it
    # is identical to the one its detail page publishes.
    assert [name for name, _url in page.breadcrumb] == [
        "Giochi di Ruolo",
        "GDR Italiano",
        "Il Richiamo di Cthulhu",
    ]

    card = next(c for c in page.cards if c.native_id == "36099")
    assert card.name == "Il Richiamo di Cthulhu - Cthulhu Invictus"
    assert card.url.endswith(".gp.36099.uw")
    assert card.code == "RDCT22"
    assert card.brand_text == "Raven Distribution"
    assert card.brand_link is not None and ".br.18.uw" in card.brand_link
    assert card.price_current == Decimal("39.99")
    assert card.currency == "EUR"
    assert card.availability == "PreOrder"  # the third state, which the June notes had missed
    assert card.description is not None and card.description.startswith("SETTEMBRE 2026")
    # The card's image path is relative on the site; it must come out usable.
    assert card.image_url is not None and card.image_url.startswith("https://")


def test_the_card_and_the_detail_page_agree_on_the_same_product() -> None:
    """Both paths must produce the same product, or a category and a single-product watch of
    one item would become two catalog rows (which is what 9.B4's de-duplication rests on)."""
    page = parse_category(_read("sp_192_cthulhu_one_page.html"), _CTHULHU_URL)
    card = next(c for c in page.cards if c.native_id == "36099")
    detail = parse_product(_read("gp_36099_preorder.html"), card.url)

    assert card.name == detail.name
    assert card.price_current == detail.price_current
    assert card.availability == detail.availability
    assert card.brand_text == detail.brand_text
    assert card.code == detail.sku


def test_a_card_with_no_price_is_reported_as_such_not_guessed() -> None:
    """Two cards on this page carry no price block. They look identical and are not the same
    thing — one is a free download, the other is withheld from sale — so the parser hands both
    up unresolved rather than calling either free."""
    page = parse_category(_read("sp_192_cthulhu_one_page.html"), _CTHULHU_URL)
    priceless = {c.native_id: c for c in page.cards if c.price_current is None}

    assert set(priceless) == {"28079", "22992"}
    assert priceless["28079"].availability == "InStock"  # a free digital download
    assert all(c.price_original is None for c in priceless.values())


def test_the_dented_label_is_read_off_the_title() -> None:
    page = parse_category(_read("sp_192_cthulhu_one_page.html"), _CTHULHU_URL)
    dented = [c for c in page.cards if "ammacc" in c.name.lower()]
    assert [c.native_id for c in dented] == ["34128"]
    # Two spellings live on the site, with and without spaces around the dash; both are just a
    # prefix, which is why detection can stay anchored (9.B5).
    assert dented[0].name.upper().startswith("AMMACCATO")


def test_discounts_appear_only_on_the_cards_that_have_one() -> None:
    page = parse_category(_read("sp_192_cthulhu_one_page.html"), _CTHULHU_URL)
    discounted = [c for c in page.cards if c.price_original is not None]
    assert len(discounted) == 6  # the rest are at full price, where the site prints no listino
    for card in discounted:
        assert card.price_current is not None and card.price_original is not None
        assert card.price_original > card.price_current


def test_a_paginated_category_declares_its_size_on_every_page() -> None:
    first = parse_category(_read("sp_115_classici_page1.html"), _CLASSICI_URL)
    second = parse_category(_read("sp_115_classici_page2.html"), page_url(_CLASSICI_URL, 2))

    assert (first.total_items, first.page_size, first.total_pages) == (1040, 50, 21)
    assert (second.total_items, second.total_pages) == (1040, 21)
    assert len(first.cards) == len(second.cards) == 50
    # Different products on the two pages: the walk must not re-read the same ones.
    assert not {c.native_id for c in first.cards} & {c.native_id for c in second.cards}


def test_only_the_cards_count_not_the_carousels() -> None:
    """The page holds 74 `h2.title` elements for 50 products — the rest are side carousels. A
    page-wide selector would invent two dozen products out of them."""
    raw = _read("sp_115_classici_page1.html").decode("cp1252", errors="replace")
    assert raw.count('<h2 class="title">') > 50
    assert len(parse_category(_read("sp_115_classici_page1.html"), _CLASSICI_URL).cards) == 50


@pytest.mark.parametrize(
    ("page", "expected"),
    [
        (1, "https://x/c.1.1.1.sp.uw?idA=9"),
        (2, "https://x/c.1.1.1.sp.uw?idA=9&pg=2"),
        (21, "https://x/c.1.1.1.sp.uw?idA=9&pg=21"),
    ],
)
def test_page_url_appends_the_page_parameter(page: int, expected: str) -> None:
    assert page_url("https://x/c.1.1.1.sp.uw?idA=9", page) == expected


def test_page_url_never_stacks_two_page_parameters() -> None:
    """Page 1 keeps the bare URL on purpose: it is the same URL the scrape cache already holds
    from the previous run, and a stray `pg=1` would miss that entry."""
    assert page_url("https://x/c.sp.uw?idA=9&pg=3", 4) == "https://x/c.sp.uw?idA=9&pg=4"
    assert page_url("https://x/c.sp.uw?idA=9&pg=3", 1) == "https://x/c.sp.uw?idA=9&pg=3"


def test_a_page_that_is_not_a_listing_is_a_parse_error() -> None:
    """ "No products" and "not a listing" must stay distinguishable: the first is a legitimate
    empty delivery, the second must never reach the delisting sweep."""
    with pytest.raises(DragonStoreParseError):
        parse_category(b"<html><body>nothing here</body></html>", _CTHULHU_URL)


def test_a_gate_served_as_200_is_still_a_gate_on_a_category() -> None:
    with pytest.raises(DragonStoreChallenge):
        parse_category(_CHALLENGE, _CTHULHU_URL)
