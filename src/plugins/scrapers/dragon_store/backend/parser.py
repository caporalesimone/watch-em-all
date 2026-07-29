"""Pure parser for a Dragon Store product page (`.gp`) — capabilities.md.

Strategy (studio ad hoc): the page exposes a JSON-LD ``Product`` (DRG-Q7), the
primary and unambiguous source — the page also embeds 20-46 *related* products,
so naive DOM scraping would pick the wrong one. We read name / price / currency /
availability / image / sku / brand from the JSON-LD, and only the **list price**
(``price_original``), which the JSON-LD omits, from the main detail table
(``tr.D1`` "P. Listino").

The page lies about its charset (declares iso-8859-1, is really windows-1252) and
mixes raw bytes with HTML entities, so we decode ``cp1252`` and ``html.unescape``
every text field.

Pure and dependency-free (stdlib only): no HTTP, no identity, no sanitising — the
plugin orchestrates those around this.
"""

from __future__ import annotations

import html
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Literal
from urllib.parse import urljoin, urlsplit

# What a watch can point at (the ``kind`` column of the plugin's watches table).
WatchKind = Literal["product", "category"]

_JSONLD_RE = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
# Since 2026-07-25 the site answers the first request of every session with an anti-bot
# interstitial ("Verifica accesso / Security Check"), served as HTTP 200 — so the status
# code tells us nothing and only the body can. Its checkbox calls this endpoint.
_CHALLENGE_RE = re.compile(r"captcha_check_ok|id=[\"']humanCheck[\"']", re.IGNORECASE)
# Their generic error page carries the real status *inside* a 200 body, e.g.
# ``<div id="pageNotFound"…><strong>429</strong> <span>Too Many Requests</span>``.
_SOFT_ERROR_RE = re.compile(
    r"id=[\"']pageNotFound[\"'].*?<strong>\s*(\d{3})\s*</strong>",
    re.IGNORECASE | re.DOTALL,
)
_LISTINO_ROW_RE = re.compile(r'<tr class="D1">(.*?)</tr>', re.IGNORECASE | re.DOTALL)
_BRAND_ROW_RE = re.compile(r'<tr class="T9">(.*?)</tr>', re.IGNORECASE | re.DOTALL)
_HREF_RE = re.compile(r'href="([^"]+)"', re.IGNORECASE)
_EU_PRICE_RE = re.compile(r"\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2}")
# URL shapes (capabilities.md § URL patterns). Anchored at the end of the path so a
# ``?pg=2`` or a fragment does not defeat them, and so ``.br.<id>.uw`` (brand) and
# ``giochi-di-ruolo.1.19.uw`` (department listing) match neither.
_PRODUCT_URL_RE = re.compile(r"\.gp\.\d+\.uw$", re.IGNORECASE)
_CATEGORY_URL_RE = re.compile(r"\.sp\.uw$", re.IGNORECASE)


class DragonStoreParseError(ValueError):
    """The page is not a parseable Dragon Store product (no JSON-LD ``Product``).

    Base of the whole family, so an existing ``except DragonStoreParseError`` still
    catches every case; the subclasses exist so the caller can *react* differently and so
    the log says what actually happened instead of "no JSON-LD", which was true but
    thoroughly misleading when the real answer was "we were served a gate".
    """


class DragonStoreChallenge(DragonStoreParseError):
    """We got the anti-bot interstitial instead of the product: the session has not been
    cleared yet. Recoverable — clear the session and ask again."""


class DragonStoreSoftError(DragonStoreParseError):
    """An error page served with HTTP 200, carrying its real status in the body."""

    def __init__(self, status: int, url: str) -> None:
        super().__init__(f"HTTP {status} error page (served as 200) for {url}")
        self.status = status


class DragonStoreRateLimited(DragonStoreSoftError):
    """The site is refusing us for going too fast (429). Not recoverable inside this run:
    the only correct answer is to stop asking."""


@dataclass
class ParsedProduct:
    """Raw fields extracted from a product page; the plugin assembles the Product."""

    name: str  # raw title (still carries marketing labels — the plugin sanitises it)
    price_current: Decimal
    price_original: Decimal | None
    currency: str
    availability: str  # schema.org token: "InStock" | "OutOfStock" | "PreOrder" | ...
    image_url: str | None
    brand_text: str | None
    brand_link: str | None  # absolute URL, or None
    sku: str | None
    price_valid_until: str | None
    category: str | None  # flat JSON-LD category string (→ extra)
    description: str | None
    breadcrumb: list[tuple[str, str | None]]  # (name, absolute url) root → leaf


def _clean(value: object) -> str | None:
    """Unescape HTML entities and trim; ``None`` for missing/non-text values."""
    if not isinstance(value, str):
        return None
    return html.unescape(value).strip() or None


def _fix_quotes(value: str | None) -> str | None:
    """Dragon Store's JSON-LD mangles apostrophes into double-quotes (e.g.
    ``Cthulhu "90`` for ``Cthulhu '90``); recover them in prose fields. The site
    never uses real double-quotes in titles, so a blanket swap is safe here."""
    return value.replace('"', "'") if value else value


def _iter_jsonld_objects(decoded: str) -> Iterator[dict[str, Any]]:
    for block in _JSONLD_RE.findall(decoded):
        try:
            data = json.loads(block.strip())
        except (json.JSONDecodeError, ValueError):
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            graph = item.get("@graph")
            if isinstance(graph, list):
                yield from (node for node in graph if isinstance(node, dict))
            else:
                yield item


def _find_product_jsonld(decoded: str) -> dict[str, Any] | None:
    for obj in _iter_jsonld_objects(decoded):
        if obj.get("@type") == "Product":
            return obj
    return None


def _breadcrumb(decoded: str, base_url: str) -> list[tuple[str, str | None]]:
    """The category breadcrumb (root → leaf) from JSON-LD ``BreadcrumbList``; each
    step's relative ``@id`` is resolved to an absolute URL. Empty if absent."""
    for obj in _iter_jsonld_objects(decoded):
        if obj.get("@type") != "BreadcrumbList":
            continue
        elements = obj.get("itemListElement")
        if not isinstance(elements, list):
            continue
        steps: list[tuple[int, str, str | None]] = []
        for index, entry in enumerate(elements):
            if not isinstance(entry, dict):
                continue
            item = entry.get("item")
            if isinstance(item, dict):
                name, ref = _clean(item.get("name")), item.get("@id") or item.get("url")
            else:
                name, ref = _clean(entry.get("name")), item if isinstance(item, str) else None
            if name is None:
                continue
            position = entry.get("position")
            order = position if isinstance(position, int) else index + 1
            steps.append((order, name, urljoin(base_url, str(ref)) if ref else None))
        steps.sort(key=lambda step: step[0])
        return [(name, url) for _order, name, url in steps]
    return []


def _to_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _parse_eu_price(text: str) -> Decimal | None:
    """``"€ 24,90"`` / ``"1.234,50 €"`` -> Decimal (comma decimal, dot thousands)."""
    match = _EU_PRICE_RE.search(text)
    if match is None:
        return None
    try:
        return Decimal(match.group(0).replace(".", "").replace(",", "."))
    except InvalidOperation:
        return None


def _availability_token(raw: object) -> str:
    if not raw:
        return ""
    return str(raw).rsplit("/", 1)[-1]  # "https://schema.org/InStock" -> "InStock"


def _list_price(decoded: str) -> Decimal | None:
    match = _LISTINO_ROW_RE.search(decoded)  # main detail table "P. Listino" row
    return _parse_eu_price(match.group(1)) if match else None


def _brand_link(decoded: str, base_url: str) -> str | None:
    row = _BRAND_ROW_RE.search(decoded)
    if row is None:
        return None
    href = _HREF_RE.search(row.group(1))
    return urljoin(base_url, href.group(1).strip()) if href else None


def classify_url(url: str) -> WatchKind | None:
    """Which kind of Dragon Store page this URL is, or ``None`` if it is neither.

    The two shapes the site uses (capabilities.md § URL patterns):

    - product ``<slug>.<l>.<idA>.<idC>.gp.<idProduct>.uw``
    - category ``<slug>.<l>.<idA>.<idC>.sp.uw`` (paginated with ``?…&pg=N``)

    Deliberately **not** categories: department pages such as ``giochi-di-ruolo.1.19.uw``,
    which carry no ``.sp.`` and list sub-categories rather than products, and brand pages
    (``.br.<id>.uw``). Both appear in the site's own breadcrumbs, so a looser rule would
    make a category watch out of a page with no product cards on it.

    Judged on **shape alone**, host included: these path endings are distinctive enough to
    be evidence on their own, the site's own links are relative (this same function
    classifies the hrefs read off a category page, not just what a user pastes), and
    pinning the host would refuse the mirrors the tests point at — which is how every
    fixture-driven test reaches this plugin.
    """
    path = urlsplit(url.strip()).path
    if _PRODUCT_URL_RE.search(path):
        return "product"
    if _CATEGORY_URL_RE.search(path):
        return "category"
    return None


def classify_page(decoded: str, url: str) -> None:
    """Raise the matching error if this is a known **non-product** page. Must run before
    looking for the JSON-LD: the site serves gates and errors with HTTP 200, so the body is
    the only evidence there is, and mistaking one for "malformed product page" costs an
    afternoon of debugging."""
    if _CHALLENGE_RE.search(decoded):
        raise DragonStoreChallenge(f"anti-bot interstitial served for {url}")
    soft = _SOFT_ERROR_RE.search(decoded)
    if soft is not None:
        status = int(soft.group(1))
        if status == 429:
            raise DragonStoreRateLimited(status, url)
        raise DragonStoreSoftError(status, url)


def parse_product(content: bytes, url: str) -> ParsedProduct:
    """Parse a Dragon Store product page. Raises a :class:`DragonStoreParseError` subclass
    if the page is a gate or an error page, or if the JSON-LD Product, the price or the
    name are missing."""
    decoded = content.decode("cp1252", errors="replace")
    classify_page(decoded, url)
    product = _find_product_jsonld(decoded)
    if product is None:
        raise DragonStoreParseError(f"no JSON-LD Product in {url}")

    offers = product.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}

    price_current = _to_decimal(offers.get("price"))
    if price_current is None:
        raise DragonStoreParseError(f"no offers.price in {url}")

    name = _fix_quotes(_clean(product.get("name")))
    if name is None:
        raise DragonStoreParseError(f"no name in {url}")

    brand = product.get("brand")
    brand_text = _clean(brand.get("name")) if isinstance(brand, dict) else _clean(brand)

    return ParsedProduct(
        name=name,
        price_current=price_current,
        price_original=_list_price(decoded),
        currency=str(offers.get("priceCurrency") or "EUR"),
        availability=_availability_token(offers.get("availability")),
        image_url=_clean(product.get("image")),
        brand_text=brand_text,
        brand_link=_brand_link(decoded, url),
        sku=_clean(product.get("sku")),
        price_valid_until=_clean(offers.get("priceValidUntil")),
        category=_clean(product.get("category")),
        description=_fix_quotes(_clean(product.get("description"))),
        breadcrumb=_breadcrumb(decoded, url),
    )
