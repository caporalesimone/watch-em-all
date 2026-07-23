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

    from src.core.alert_engine import AlertEvent
    from src.core.contracts import Adjustment, ConfigField, DeltaCounters, Product
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


class NotifierDeliveryError(RuntimeError):
    """A notifier failed to deliver after its own retries (NOT-R5). The message is
    user-readable ("channel unreachable", "authentication failed", …): the core records it
    verbatim as the failure reason on the ``alert_delivery`` row and logs a warning. A
    notifier must raise this (never swallow the error, never retry forever)."""


class NotifierPlugin(BasePlugin):
    """Notifier family (notifier-plugin.md). Phase 7 gives the marker base its real contract.

    A notifier is the translator between the notification content (the core decides *when*
    and *what*) and a delivery channel (it decides *how to format* and *where to send*). The
    core writes the in-app history, iterates the user's active channels, merges the admin+user
    config (user keys filtered on the user schema), passes the user's locale and records the
    per-channel outcome; the plugin declares its config schema, formats the payload and sends.

    Config is two-level (NOT-R2): ``get_admin_config_schema`` (channel infrastructure, e.g. an
    SMTP server) and ``get_user_config_schema`` (personal delivery target). Both default to
    empty — a channel entirely personal declares no admin fields; a channel with no per-user
    field declares no user fields. ``display_name`` is a human label for the channel."""

    display_name: str = ""

    def get_admin_config_schema(self) -> list[ConfigField]:
        """System-level config fields (channel infrastructure). Default: none (CFG-R1)."""
        return []

    def get_user_config_schema(self) -> list[ConfigField]:
        """Per-user config fields (personal delivery target). Default: none (CFG-R1)."""
        return []

    def send(self, notification: AlertEvent, config: dict[str, Any], locale: str) -> None:
        """Format ``notification`` for the channel (in ``locale``, with the plugin's own
        backend translations) and deliver it. ``config`` is the admin+user merge already done
        and filtered by the core. On a transient error retry a few times with backoff, then
        raise :class:`NotifierDeliveryError` with a readable reason (NOT-R5). Phase 7 delivers
        only the ``alert_digest`` payload; summary/text messages arrive later. The base raises
        so a notifier that forgets to implement it fails loudly."""
        raise NotImplementedError(f"{self.plugin_id}: send not implemented")

    def send_test(self, config: dict[str, Any], locale: str) -> None:
        """Send a **test** notification with the current merged config (NOT-R6), invoked by the
        user (own target) and the admin (channel check). No persistence. Same error contract as
        :meth:`send`. Default raises; a real notifier overrides it."""
        raise NotImplementedError(f"{self.plugin_id}: send_test not implemented")
