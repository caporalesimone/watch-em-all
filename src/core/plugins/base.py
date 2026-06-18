"""Plugin base contracts (2.B2, plugin-architecture.md).

Two families derive from a common base. Phase 2 keeps the contract minimal: the
type-specific runtime methods (run_for_user, send, config schemas, ...) arrive in
later phases. A plugin instance is exported as `plugin` from its backend entry
(2.B2 decision) and its `plugin_id` must equal the manifest `name`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter

if TYPE_CHECKING:
    from src.core.plugins.context import PluginContext


class BasePlugin:
    """Common contract for every plugin, with default (no-op) implementations."""

    plugin_id: str  # must equal the manifest `name` (validated at load)

    def initialize(self, context: PluginContext) -> None:
        """Called once at load. The plugin creates its own tables here,
        idempotently (CTX-R6). Default: no-op (e.g. notifiers without tables)."""

    def router(self) -> APIRouter | None:
        """An APIRouter mounted under /api/{route_base}, or None for no routes."""
        return None

    def delete_user_data(self, context: PluginContext, user_id: int) -> None:
        """Idempotently remove this user's rows from the plugin's tables (USR-R10).
        Default: no-op (plugins without per-user data)."""


class ScraperPlugin(BasePlugin):
    """Scraper family. Phase 2: marker base; run/config contracts land later."""


class NotifierPlugin(BasePlugin):
    """Notifier family. Phase 2: marker base; send/config contracts land later."""
