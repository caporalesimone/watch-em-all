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
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

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
    price_current: Decimal | None  # None = the site shows no price (9.B2b resolves it)
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

    Judged on the **path alone**: the host is never looked at. Those path endings are
    distinctive enough to be evidence on their own; the site's own links are relative (this
    same function classifies hrefs read off a category page, not only what a user pastes);
    and pinning the host would refuse the local mirrors every fixture-driven test points at.
    The cost is accepted and small: a URL of the right shape on somebody else's host is
    classified, and then fails at the first request.
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
    if the page is a gate or an error page, or if the JSON-LD ``Product`` or the name are
    missing. A missing **price** is not a failure — see ``price_current``."""
    decoded = content.decode("cp1252", errors="replace")
    classify_page(decoded, url)
    product = _find_product_jsonld(decoded)
    if product is None:
        raise DragonStoreParseError(f"no JSON-LD Product in {url}")

    offers = product.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}

    # A missing price is NOT a parse failure (9.B2b). The site legitimately offers some
    # products without one: a free digital download has neither price nor list price, while a
    # product withheld from sale keeps its "P. Listino" row. Raising here made both of them
    # unwatchable, and worse, made them absent from a run's delivery — which the delisting
    # sweep reads as "gone from the site". The plugin decides what such a product costs.
    price_current = _to_decimal(offers.get("price"))

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


# --- category listing (9.B2/9.B3) ------------------------------------------------------
#
# A listing page carries everything the catalog needs, verified field by field over 139 real
# cards, and its native id yields the same external_id as the product page — which is what
# makes de-duplication between a category and a single-product watch possible at all.
# Everything is read **scoped to a card**: the page also holds side carousels using the same
# ``h2.title`` markup (74 titles for 50 cards on the sample), so page-wide selectors would
# invent products.
_CARD_RE = re.compile(
    r'<div class="resultBox prod" id="r_(?P<id>\d+)">(?P<body>.*?)'
    r'(?=<div class="resultBox prod"|<div id="footer|</body>)',
    re.IGNORECASE | re.DOTALL,
)
# "39 risultati trovati (50 per pagina - 1 in totale)" — item count, page size and page count,
# printed above and below the list. This is what lets a progress bar be determinate from the
# first request instead of guessing.
_PAGES_RE = re.compile(
    r"(?P<items>\d+)\s+risultati\s+trovati\s*\(\s*(?P<size>\d+)\s+per\s+pagina\s*-\s*"
    r"(?P<pages>\d+)\s+in\s+totale\s*\)",
    re.IGNORECASE,
)
_CARD_LINK_RE = re.compile(r'<h2 class="title"><a[^>]*href="([^"]+)"', re.IGNORECASE)
_CARD_TITLE_RE = re.compile(r'<h2 class="title"><a[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
_CARD_IMG_RE = re.compile(r'class="imageLink"[^>]*>\s*<img[^>]*src="([^"]+)"', re.IGNORECASE)
_CARD_CODE_RE = re.compile(r'<dd class="code"[^>]*>(.*?)</dd>', re.IGNORECASE | re.DOTALL)
_CARD_BRAND_RE = re.compile(
    r'<dd class="T9"[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL
)
_CARD_DESC_RE = re.compile(r'<p class="description">(.*?)</p>', re.IGNORECASE | re.DOTALL)
_CARD_PRICE_RE = re.compile(r'<span class="mainPriceAmount">(.*?)</span>', re.IGNORECASE)
_CARD_CURRENCY_RE = re.compile(r'<span class="mainPriceCurrency">(.*?)</span>', re.IGNORECASE)
_CARD_LIST_PRICE_RE = re.compile(r'grossPriceAmount"[^>]*>(.*?)<', re.IGNORECASE | re.DOTALL)
_CARD_AVAIL_RE = re.compile(r'<span class="(fullAV|noAV|inArrivalAV)">', re.IGNORECASE)
# The card's availability spans mapped onto the schema.org tokens the product page uses, so
# both paths hand the plugin the same three states and it needs one mapping, not two.
_AVAIL_TOKENS = {"fullav": "InStock", "noav": "OutOfStock", "inarrivalav": "PreOrder"}
_CURRENCY_NAMES = {"€": "EUR", "eur": "EUR"}


@dataclass
class ParsedCard:
    """One product as a listing card shows it (9.B2).

    ``price_current`` is ``None`` when the card carries no price block at all — 2-4% of a real
    category. Those are two situations that look identical here and are told apart only by
    availability: a free digital download, and a product withheld from sale whose detail page
    still carries a list price. The plugin resolves them from that page; the parser refuses to
    guess, because guessing "free" on the second one puts a 25-euro game in the catalog at
    zero and fires a price-drop alert.
    """

    native_id: str
    url: str  # absolute
    name: str  # raw title (still carries labels — the plugin sanitises it)
    code: str | None  # article code (becomes the product's sku)
    brand_text: str | None
    brand_link: str | None  # absolute
    image_url: str | None  # absolute (the card's own path is relative)
    price_current: Decimal | None
    price_original: Decimal | None  # only present when discounted
    currency: str
    availability: str  # schema.org token, mapped from the card's span
    description: str | None  # the card's one-line abstract, not the full text


@dataclass
class ParsedCategory:
    """A listing page: its cards plus what it says about the set they belong to."""

    cards: list[ParsedCard]
    total_items: int | None
    page_size: int | None
    total_pages: int | None
    breadcrumb: list[tuple[str, str | None]]  # the page's own, shared by all its cards


def _card_text(pattern: re.Pattern[str], body: str) -> str | None:
    match = pattern.search(body)
    return _clean(match.group(1)) if match else None


def _parse_card(native_id: str, body: str, base_url: str) -> ParsedCard | None:
    """One card, or ``None`` when it has no title or link — then it is not a product card."""
    link = _CARD_LINK_RE.search(body)
    name = _card_text(_CARD_TITLE_RE, body)
    if link is None or name is None:
        return None
    image = _CARD_IMG_RE.search(body)
    brand = _CARD_BRAND_RE.search(body)
    price_text = _card_text(_CARD_PRICE_RE, body)
    list_text = _card_text(_CARD_LIST_PRICE_RE, body)
    currency_text = (_card_text(_CARD_CURRENCY_RE, body) or "").strip().lower()
    availability = _CARD_AVAIL_RE.search(body)
    return ParsedCard(
        native_id=native_id,
        url=urljoin(base_url, link.group(1).strip()),
        name=_fix_quotes(name) or name,
        code=_card_text(_CARD_CODE_RE, body),
        brand_text=_fix_quotes(_clean(brand.group(2))) if brand else None,
        brand_link=urljoin(base_url, brand.group(1).strip()) if brand else None,
        image_url=urljoin(base_url, image.group(1).strip()) if image else None,
        price_current=_parse_eu_price(price_text) if price_text else None,
        price_original=_parse_eu_price(list_text) if list_text else None,
        currency=_CURRENCY_NAMES.get(currency_text, "EUR"),
        availability=_AVAIL_TOKENS.get(
            availability.group(1).lower() if availability else "", "Unknown"
        ),
        description=_fix_quotes(_card_text(_CARD_DESC_RE, body)),
    )


def parse_category(content: bytes, url: str) -> ParsedCategory:
    """Parse a Dragon Store category page.

    Raises a :class:`DragonStoreParseError` subclass for a gate or an error page, or when the
    page holds neither cards nor a result header: "this category has no products" has to stay
    distinguishable from "this is not a listing", since the first is a legitimate empty
    delivery and the second must never reach the delisting sweep.
    """
    decoded = content.decode("cp1252", errors="replace")
    classify_page(decoded, url)

    cards: list[ParsedCard] = []
    for match in _CARD_RE.finditer(decoded):
        card = _parse_card(match.group("id"), match.group("body"), url)
        if card is not None:
            cards.append(card)

    header = _PAGES_RE.search(decoded)
    if header is None and not cards:
        raise DragonStoreParseError(f"no product cards and no result header in {url}")

    return ParsedCategory(
        cards=cards,
        total_items=int(header.group("items")) if header else None,
        page_size=int(header.group("size")) if header else None,
        total_pages=int(header.group("pages")) if header else None,
        breadcrumb=_breadcrumb(decoded, url),
    )


def page_url(url: str, page: int) -> str:
    """The URL of page *n* of a category (9.B3): the site paginates with a plain ``&pg=N``,
    server-rendered, no AJAX. Page 1 keeps the bare URL, so re-reading a category hits the
    same cache entry the previous run filled."""
    if page <= 1:
        return url
    split = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(split.query, keep_blank_values=True) if k != "pg"]
    query.append(("pg", str(page)))
    return urlunsplit(split._replace(query=urlencode(query)))
