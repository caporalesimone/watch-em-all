"""Plugin Context — the object handed to every plugin in ``initialize()`` and
rebuilt per scrape for the runtime.

The type is defined here (used by the registry's contract from 2.B2); the real
factory that builds it from the core engine/logger/config is wired in 2.B3
(:func:`build_context`).

Phase-3 PR2 adds ``update_catalog``: a callback bound to this context's session
and the calling plugin's ``plugin_id``, so a scraper delivers its products with
``context.update_catalog(user_id, products)`` and never writes the catalog
directly (the Catalog Update Service does, and commits — catalog-update-service.md).

``http`` is the polite, counted, retrying HTTP client every scraper must use
(SCR-R6, plugin-context.md CTX-R1..R4), backed by the per-plugin scrape cache
(CTX-R9, 4.B8). Phase 4 (4.B10) governs its politeness/timeout and the cache
half-life from the per-scraper admin **reserved config** (``scraper_config``).

Still simplified (declared, flow rule #7): ``logger`` writes to stdout (the
``system_log`` handler is attached at the process level, 4.B7); ``config`` (the
plugin's *own* declared fields) stays empty until the ConfigField infrastructure
lands (phase 7+) — the core reserved keys live in ``scraper_config``, not here;
no ``markdown`` yet.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from logging import Logger
from typing import TYPE_CHECKING, Any

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from src.core.catalog import forget_source as _forget_source_service
from src.core.catalog import update_catalog as _update_catalog_service
from src.core.catalog import upsert_products as _upsert_products_service
from src.core.db import get_engine, new_session
from src.core.http import HttpClient
from src.core.scrape_cache import ScrapeCache
from src.core.scraper_config import get_scraper_config

if TYPE_CHECKING:
    from src.core.contracts import DeltaCounters, Product
    from src.core.plugins.base import BasePlugin
    from src.core.plugins.manifest import Manifest

# (user_id, current products) -> delta counters. Bound to a session + plugin_id.
UpdateCatalog = Callable[[int, "list[Product]"], "DeltaCounters"]
# (user_id, source_key) -> provenance rows dropped. Bound to a session + plugin_id.
ForgetSource = Callable[[int, str], int]


def _no_catalog_write(user_id: int, products: list[Product]) -> DeltaCounters:
    """Default for a context built without that write path: raising beats silently
    dropping a delivery, and beats defaulting to a path the caller did not choose."""
    raise NotImplementedError("this context has no catalog write path")


def bind_forget_source(session: Session, plugin_id: str) -> ForgetSource:
    """Bound :func:`catalog.forget_source`: what a plugin calls when one of a user's inputs
    ceases to exist, so the products it delivered stop claiming they still come from it."""

    def _forget(user_id: int, source_key: str) -> int:
        return _forget_source_service(session, user_id, plugin_id, source_key)

    return _forget


def bind_upsert_catalog(session: Session) -> UpdateCatalog:
    """The **non-delisting** write path bound to a session (:func:`catalog.upsert_products`).

    Exposed so the paths that build their own context — a watch resolved as it is added —
    get the core's write path instead of reaching into ``src.core.catalog`` themselves.
    """

    def _upsert(user_id: int, products: list[Product]) -> DeltaCounters:
        return _upsert_products_service(session, user_id, products)

    return _upsert


@dataclass
class PluginContext:
    """Everything a plugin may use, and by convention nothing else."""

    engine: Engine  # to create the plugin's OWN tables (own MetaData) in initialize()
    db: Session  # a session scoped to the plugin's own tables (plugin_<name>_*)
    logger: Logger  # namespaced; phase 2 -> stdout (system_log lands later)
    config: Mapping[str, Any]  # the plugin's admin-config section (empty in phase 2)
    update_catalog: UpdateCatalog  # deliver a COMPLETE delivery (delists what is missing)
    # Deliver a delivery that says nothing about the rest of the catalog — a single product
    # resolved as its watch is added, or a run that failed to read the site. Never delists.
    upsert_catalog: UpdateCatalog = _no_catalog_write
    http: HttpClient = field(default_factory=HttpClient)  # polite/counted/retrying client (SCR-R6)
    # Tell the core an input is gone, so the products it delivered stop naming it as a source
    # (C14). Defaults to a no-op: a scraper with no notion of inputs never records provenance,
    # so there is nothing for it to forget — unlike a missing write path, which is a mistake.
    forget_source: ForgetSource = lambda user_id, source_key: 0  # noqa: E731


def build_context(manifest: Manifest, plugin: BasePlugin) -> PluginContext:
    """The default context factory (2.B3): wires the core engine, a fresh session,
    a per-plugin namespaced logger (stdout for now), an empty admin config, and the
    ``update_catalog`` callback bound to that session and this plugin's ``plugin_id``.

    Called at load (``initialize``) and again per scrape (a fresh session each time;
    the caller closes ``ctx.db`` when the scrape ends).
    """
    session = new_session()
    plugin_id = plugin.plugin_id

    def _update_catalog(user_id: int, products: list[Product]) -> DeltaCounters:
        return _update_catalog_service(session, user_id, plugin_id, products)

    _upsert_catalog = bind_upsert_catalog(session)

    logger = logging.getLogger(f"wea.plugin.{manifest.name}")
    return PluginContext(
        engine=get_engine(),
        db=session,
        logger=logger,
        config={},
        update_catalog=_update_catalog,
        upsert_catalog=_upsert_catalog,
        forget_source=bind_forget_source(session, plugin_id),
        http=build_http_client(session, plugin_id, logger),
    )


def build_http_client(
    session: Session,
    plugin_id: str,
    logger: Logger,
    *,
    sleep: Callable[[float], None] | None = None,
) -> HttpClient:
    """The configured client for a scraper: politeness, timeout and cache half-life from
    the core reserved admin config (4.B10), plus the per-plugin scrape cache (CTX-R9) and
    ``robots.txt`` compliance (CTX-R10). Defaults mirror the module constants when no
    admin override exists.

    Shared on purpose. Every path that talks to a site must get *this* client — a
    scheduled run, the manual scrape-now, and the paths that build their own context
    (resolving a watch as it is added). A hand-rolled ``HttpClient()`` in one of those
    would silently bypass the admin config and the cache, which is exactly how a scraper
    ends up hammering a site nobody configured it to hammer.

    ``sleep`` replaces how the client waits out its politeness interval. A cancellable job
    passes one that returns early (9.X6f): most of a scrape's wall-clock is that wait, so
    without this a cancellation would only take effect after the 11 seconds it was already
    sleeping through.
    """
    cfg = get_scraper_config(session, plugin_id)
    extra: dict[str, Any] = {"sleep": sleep} if sleep is not None else {}
    return HttpClient(
        timeout_s=cfg.http_timeout_s,
        min_interval_s=cfg.politeness_delay_ms / 1000,
        cache=ScrapeCache(get_engine(), plugin_id, ttl_min=cfg.cache_ttl_min),
        # The client logs under the plugin's own namespace so one log stream tells the
        # whole story of a run: robots.txt, politeness, cache hits, failures.
        logger=logger,
        **extra,
    )
