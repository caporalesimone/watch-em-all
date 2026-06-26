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

from src.core.catalog import update_catalog as _update_catalog_service
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


@dataclass
class PluginContext:
    """Everything a plugin may use, and by convention nothing else."""

    engine: Engine  # to create the plugin's OWN tables (own MetaData) in initialize()
    db: Session  # a session scoped to the plugin's own tables (plugin_<name>_*)
    logger: Logger  # namespaced; phase 2 -> stdout (system_log lands later)
    config: Mapping[str, Any]  # the plugin's admin-config section (empty in phase 2)
    update_catalog: UpdateCatalog  # deliver products to the core (the only write path)
    http: HttpClient = field(default_factory=HttpClient)  # polite/counted/retrying client (SCR-R6)


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

    # Core reserved config for this scraper (4.B10): admin-set politeness/timeout/cache
    # half-life, read here for both scheduled runs and the manual scrape-now. Defaults
    # mirror the former constants when no admin override exists.
    cfg = get_scraper_config(session, plugin_id)

    return PluginContext(
        engine=get_engine(),
        db=session,
        logger=logging.getLogger(f"wea.plugin.{manifest.name}"),
        config={},
        update_catalog=_update_catalog,
        # Polite/counted/retrying client (SCR-R6) + per-plugin scrape cache (CTX-R9),
        # both governed by the admin reserved config; transparent to the plugin.
        http=HttpClient(
            timeout_s=cfg.http_timeout_s,
            min_interval_s=cfg.politeness_delay_s,
            cache=ScrapeCache(get_engine(), plugin_id, ttl_min=cfg.cache_ttl_min),
        ),
    )
