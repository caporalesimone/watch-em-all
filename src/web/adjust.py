"""Binding the plugins' ``get_adjustments`` for cart evaluation, from the web side.

The cart engine and the alert engine take a bound ``get_adjustments`` (or an
``AdjusterProvider``) so the core never imports the plugins. This resolves it from the
loaded plugins on ``app.state`` — shared by the carts API and the alert-cadence API.
"""

from __future__ import annotations

from fastapi import Request

from src.core.alert_engine import AdjusterProvider
from src.core.cart_engine import AdjustmentFn
from src.core.models import Cart
from src.core.plugins.base import ScraperPlugin
from src.core.plugins.registry import LoadedPlugin


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


def make_adjuster_provider(request: Request) -> AdjusterProvider:
    """An :data:`AdjusterProvider` bound to the request's loaded scrapers (for the alert
    engine, which resolves adjustments per cart across a whole run)."""
    scrapers = loaded_scrapers(request)

    def provider(cart: Cart) -> AdjustmentFn | None:
        if cart.mode != "scraper_specific" or cart.scraper_id is None:
            return None
        plugin = scrapers.get(cart.scraper_id)
        return plugin.get_adjustments if plugin is not None else None

    return provider
