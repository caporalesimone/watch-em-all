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
from typing import Any
from urllib.parse import urljoin

_JSONLD_RE = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
_LISTINO_ROW_RE = re.compile(r'<tr class="D1">(.*?)</tr>', re.IGNORECASE | re.DOTALL)
_BRAND_ROW_RE = re.compile(r'<tr class="T9">(.*?)</tr>', re.IGNORECASE | re.DOTALL)
_HREF_RE = re.compile(r'href="([^"]+)"', re.IGNORECASE)
_EU_PRICE_RE = re.compile(r"\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2}")


class DragonStoreParseError(ValueError):
    """The page is not a parseable Dragon Store product (no JSON-LD ``Product``)."""


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
    category: str | None
    description: str | None


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


def parse_product(content: bytes, url: str) -> ParsedProduct:
    """Parse a Dragon Store product page. Raises ``DragonStoreParseError`` if the
    JSON-LD Product, the price or the name are missing."""
    decoded = content.decode("cp1252", errors="replace")
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
    )
