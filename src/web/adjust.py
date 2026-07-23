"""Binding the plugins' ``get_adjustments`` for cart evaluation, from the web side.

The cart engine and the alert engine take a bound ``get_adjustments`` (or an
``AdjusterProvider``) so the core never imports the plugins. Two ways to resolve it:

- request-scoped (``adjuster_for`` / ``loaded_scrapers``) for the carts API, and
- a process registry (``register_scrapers`` at startup) for code with no ``Request`` —
  the event-driven alert run after a manual scrape (scrape-now / TP simulate) runs in a
  background task or a plugin route, where there is no request to read ``app.state`` from.
"""

from __future__ import annotations

import logging

from fastapi import Request
from sqlalchemy.orm import Session

from src.core.alert_engine import AdjusterProvider, run_for_user
from src.core.cart_engine import AdjustmentFn
from src.core.models import Cart
from src.core.notify import enqueue_deliveries
from src.core.plugins.base import NotifierPlugin, ScraperPlugin
from src.core.plugins.registry import LoadedPlugin

log = logging.getLogger(__name__)

# Loaded scraper instances by plugin_id, populated once at app startup (register_scrapers).
_registry: dict[str, ScraperPlugin] = {}

# Loaded notifier instances, populated at startup — the event-driven alert run enqueues their
# per-channel deliveries after writing a digest (the worker drains the pending ones).
_notifiers: list[NotifierPlugin] = []


def register_scrapers(loaded_plugins: list[LoadedPlugin]) -> None:
    """Cache the loaded scraper plugins at startup so the alert run can bind adjustments
    without a request (scrape-now background task, plugin routes)."""
    _registry.clear()
    for lp in loaded_plugins:
        if isinstance(lp.plugin, ScraperPlugin):
            _registry[lp.plugin.plugin_id] = lp.plugin


def register_notifiers(loaded_plugins: list[LoadedPlugin]) -> None:
    """Cache the loaded notifier plugins at startup so the event-driven alert run can enqueue
    per-channel deliveries (scrape-now / TP simulate)."""
    _notifiers.clear()
    for lp in loaded_plugins:
        if isinstance(lp.plugin, NotifierPlugin):
            _notifiers.append(lp.plugin)


def loaded_scrapers(request: Request) -> dict[str, ScraperPlugin]:
    """Loaded scraper instances keyed by plugin_id (targets for scraper_specific carts)."""
    loaded: list[LoadedPlugin] = list(getattr(request.app.state, "loaded_plugins", []))
    return {lp.plugin.plugin_id: lp.plugin for lp in loaded if isinstance(lp.plugin, ScraperPlugin)}


def adjuster_for(request: Request, cart: Cart) -> AdjustmentFn | None:
    """Bind the cart's scraper ``get_adjustments`` for a scraper_specific cart, else None
    (cross carts, or the scraper is not loaded → no adjustments)."""
    if cart.mode != "scraper_specific" or cart.scraper_id is None:
        return None
    plugin = loaded_scrapers(request).get(cart.scraper_id)
    return plugin.get_adjustments if plugin is not None else None


def _registry_provider(cart: Cart) -> AdjustmentFn | None:
    """An :data:`AdjusterProvider` backed by the startup registry (no request needed)."""
    if cart.mode != "scraper_specific" or cart.scraper_id is None:
        return None
    plugin = _registry.get(cart.scraper_id)
    return plugin.get_adjustments if plugin is not None else None


def run_user_alerts(db: Session, user_id: int) -> None:
    """Event-driven alert run after a manual scrape (scrape-now / TP simulate): diff the
    user's carts against their baselines and write at most one aggregated digest. Failures
    are logged, never surfaced to the triggering request."""
    provider: AdjusterProvider = _registry_provider
    try:
        result = run_for_user(db, user_id, provider)
        if result is not None:
            enqueue_deliveries(db, result, _notifiers)  # per-channel rows; in-app inline
    except Exception:
        db.rollback()
        log.exception("alert run failed for user %s", user_id)
