"""Plugin base contracts (2.B2, plugin-architecture.md).

Two families derive from a common base. A plugin instance is exported as
`plugin` from its backend entry (2.B2 decision) and its `plugin_id` must equal
the manifest `name`.

Scrapers add the identity template-method (SCR-R10 / product.md): the plugin
supplies only the SEED (``identity_seed``, abstract — a scraper without it does
not load); normalisation and hashing are FINAL and identical for every scraper,
so the same product always maps to the same ``external_id`` across processes
(worker vs web). The runtime methods (``run_for_user`` / ``run_test``) arrive
with the scraper runtime; their write path is the ``context.update_catalog``
callback (the scraper never writes the catalog directly).
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, final
from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter

from src.core.contracts import CategoryRef

if TYPE_CHECKING:
    from decimal import Decimal

    from sqlalchemy import MetaData

    from src.core.contracts import Adjustment, DeltaCounters, Product
    from src.core.models import CatalogProduct
    from src.core.plugins.context import PluginContext


class Tags:
    """Per-product accumulator of tags (``tags``, SCR-R16 / PROD-R5).

    The base provides the *mechanism*; what to add is the plugin's choice (a label
    cleaned off the title, a special availability state, …). One instance per
    product being built — never stored on the (singleton) plugin instance, so tags
    never leak across products/users. Strings are trimmed of surrounding whitespace
    and separator symbols, and deduplicated.
    """

    _STRIP = " \t\r\n-–—:|·"

    def __init__(self) -> None:
        self._items: list[str] = []

    def add_tag(self, value: str) -> None:
        cleaned = value.strip(self._STRIP).strip()
        if cleaned and cleaned not in self._items:
            self._items.append(cleaned)

    def get_tags(self) -> list[str]:
        return list(self._items)


class CategoryPath:
    """Per-product category breadcrumb builder (``category``, SCR-R17 / PROD-R7).

    The base provides the mechanism; the plugin calls ``add_child(name, url)`` from
    root to leaf as it discovers the path, then ``get_path()`` returns the ordered
    list. One instance per product (never on the singleton plugin instance)."""

    def __init__(self) -> None:
        self._items: list[CategoryRef] = []

    def add_child(self, name: str, url: str | None = None) -> None:
        text = name.strip()
        if text:
            self._items.append(CategoryRef(text=text, link=url))

    def get_path(self) -> list[CategoryRef]:
        return list(self._items)


class BasePlugin:
    """Common contract for every plugin, with default (no-op) implementations."""

    plugin_id: str  # must equal the manifest `name` (validated at load)

    # A plugin that owns tables (named ``plugin_<plugin_id>_*``) MUST declare them by
    # pointing this at its own MetaData (``table_metadata = _Base.metadata``); ``None``
    # means "no tables" (e.g. a notifier without state). The registry enforces it at
    # load (DB-R7) and the schema-drift guard (4.B0) iterates it next to the core.
    table_metadata: MetaData | None = None

    def initialize(self, context: PluginContext) -> None:
        """Called once at load. The plugin creates its own tables here,
        idempotently (CTX-R6). Default: no-op (e.g. notifiers without tables)."""

    def router(self) -> APIRouter | None:
        """An APIRouter mounted under /api/{route_base}, or None for no routes."""
        return None

    def delete_user_data(self, context: PluginContext, user_id: int) -> None:
        """Idempotently remove this user's rows from the plugin's tables (USR-R10).
        Default: no-op (plugins without per-user data)."""


class ScraperPlugin(BasePlugin, ABC):
    """Scraper family (scraper-plugin.md).

    Identity is a template method (SCR-R10): the plugin implements only
    ``identity_seed``; ``normalize_url`` / ``_stable_id`` / ``external_id_for``
    are ``final`` and uniform for all scrapers. ``run_for_user`` / ``run_test``
    are the runtime entry points (real scrapers override them).
    """

    @abstractmethod
    def identity_seed(self, raw: Any) -> str | None:
        """The site-specific identity seed, the ONLY site-specific point of the
        identity. Returns the native SKU/ID (preferred — stable by construction),
        or ``None`` to fall back to the URL. NEVER titles/descriptions: they
        change. Being abstract, a scraper that omits it does not instantiate, so
        the registry rejects it at load instead of breaking history in production.
        """

    @final
    @staticmethod
    def normalize_url(url: str) -> str:
        """Drop volatile query/fragment, lowercase the host, strip the trailing
        slash. FINAL: identical for every scraper."""
        p = urlsplit(url.strip())
        return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/"), "", ""))

    @final
    @staticmethod
    def _stable_id(seed: str) -> str:
        """Any string -> a fixed 16-hex (64-bit) id, deterministic across
        processes. NEVER the built-in ``hash()`` (randomised by PYTHONHASHSEED)."""
        return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]

    @final
    def external_id_for(self, raw: Any, url: str) -> str:
        """Orchestration: plugin seed -> URL fallback -> uniform hashing. The
        plugin never fills ``external_id`` by hand; it calls this when building a
        ``Product``."""
        return self._stable_id(self.identity_seed(raw) or self.normalize_url(url))

    @staticmethod
    def new_tags() -> Tags:
        """A fresh per-product tag accumulator (SCR-R16). Use one per product;
        add tags via ``add_tag`` and read them back with ``get_tags``."""
        return Tags()

    @staticmethod
    def new_category() -> CategoryPath:
        """A fresh per-product category breadcrumb builder (SCR-R17). Use one per
        product; ``add_child(name, url)`` root → leaf, then ``get_path()``."""
        return CategoryPath()

    def run_for_user(self, context: PluginContext, user_id: int) -> DeltaCounters:
        """Scrape this user's inputs and deliver the current products through
        ``context.update_catalog`` (the only write path), returning the delta
        counters. The default raises so a misconfigured scraper fails loudly;
        real scrapers override it."""
        raise NotImplementedError(f"{self.plugin_id}: run_for_user not implemented")

    def run_test(self, context: PluginContext, params: dict[str, Any]) -> list[Product]:
        """Dry-run (SCR-R11): produce the products for UI-provided ``params``
        WITHOUT writing anything (neither catalog nor inputs). Real scrapers
        override it."""
        raise NotImplementedError(f"{self.plugin_id}: run_test not implemented")

    def configured_users(self, context: PluginContext) -> list[int]:
        """User ids that have configured this scraper — the users a SCHEDULED run
        iterates (SCR-R3 reframed: the scraper tells the core whom to scrape). Default:
        none; a real scraper returns e.g. the users with at least one watch. Not used by
        scrape-now, which targets only the requesting user."""
        return []

    def get_adjustments(
        self, products: list[CatalogProduct], cart_total: Decimal
    ) -> list[Adjustment]:
        """Adjustments for a scraper_specific cart (adjustment.md, 5.B5): the plugin's
        site rules (threshold discounts, shipping, …) applied to the cart's **active**
        products and their discounted ``cart_total``. Returns signed ``Adjustment``
        items the core sums into the final estimate. Default: none — a scraper without
        site-specific cart logic returns ``[]``."""
        return []


class NotifierPlugin(BasePlugin):
    """Notifier family. Phase 2: marker base; send/config contracts land later."""
