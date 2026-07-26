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
