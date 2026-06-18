"""Plugin registry: discover, validate, load and mount plugins (2.B2, REG-*).

Runs the deterministic load sequence (plugin-registry.md) for every plugin under
``src/plugins/{scrapers,notifiers}/``. A plugin that fails any step is rejected
and logged; the core and the other plugins keep running (REG-R5). The activation
is static (manifest `enabled`); there is no runtime plugin switching.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

from fastapi import FastAPI

from src.core.plugins.base import BasePlugin, NotifierPlugin, ScraperPlugin
from src.core.plugins.context import PluginContext, build_context
from src.core.plugins.manifest import Manifest, ManifestError, PluginType, parse_manifest

log = logging.getLogger(__name__)

# src/plugins, resolved from this file (src/core/plugins/registry.py).
PLUGINS_ROOT = Path(__file__).resolve().parents[2] / "plugins"

_FOLDERS: tuple[tuple[PluginType, str], ...] = (
    ("scraper", "scrapers"),
    ("notifier", "notifiers"),
)
_EXPECTED_BASE: dict[PluginType, type[BasePlugin]] = {
    "scraper": ScraperPlugin,
    "notifier": NotifierPlugin,
}

# Builds the dedicated context for a plugin (the real one is wired in 2.B3).
ContextBuilder = Callable[[Manifest, BasePlugin], PluginContext]


class PluginLoadError(RuntimeError):
    """A plugin passed manifest validation but failed to import or initialise."""


@dataclass(frozen=True)
class LoadedPlugin:
    """A plugin that loaded successfully, kept for discovery and dispatch."""

    manifest: Manifest
    plugin: BasePlugin
    directory: Path  # the plugin's folder on disk (to resolve its icon asset)


def load_plugins(
    app: FastAPI | None,
    *,
    context_builder: ContextBuilder = build_context,
    plugins_root: Path = PLUGINS_ROOT,
    router_dependencies: list[Any] | None = None,
) -> list[LoadedPlugin]:
    """Discover and load every enabled plugin; return the loaded ones.

    ``app`` receives each plugin's router under ``/api{route_base}``. Pass None in
    the worker, which loads plugins (``initialize``) but serves no HTTP.
    ``router_dependencies`` (e.g. ``[Depends(require_user)]``) are applied to every
    plugin router so all plugin routes sit behind authentication; the dependency is
    injected by the web app to keep the core decoupled from the auth layer.
    """
    loaded: list[LoadedPlugin] = []
    names: set[str] = set()
    for folder_type, folder in _FOLDERS:
        base = plugins_root / folder
        if not base.is_dir():
            continue
        for plugin_dir in sorted(p for p in base.iterdir() if p.is_dir()):
            try:
                _load_one(
                    app,
                    folder_type,
                    plugin_dir,
                    names,
                    loaded,
                    context_builder,
                    router_dependencies,
                )
            except Exception as exc:  # REG-R5: isolate the failure, keep going.
                log.error("plugin %s rejected: %s", plugin_dir.name, exc)
    return loaded


def _load_one(
    app: FastAPI | None,
    folder_type: PluginType,
    plugin_dir: Path,
    names: set[str],
    loaded: list[LoadedPlugin],
    context_builder: ContextBuilder,
    router_dependencies: list[Any] | None,
) -> None:
    manifest = parse_manifest(plugin_dir / "manifest.json", folder_type=folder_type)
    if not manifest.enabled:
        log.info("plugin %s is disabled, skipping", manifest.name)
        return
    if manifest.name in names:
        raise ManifestError(f"duplicate plugin name {manifest.name!r}")

    module = _import_entry(manifest.name, plugin_dir / manifest.backend.entry)
    plugin = getattr(module, "plugin", None)
    if not isinstance(plugin, BasePlugin):
        raise PluginLoadError(
            f"{manifest.name}: backend must export a `plugin` BasePlugin instance"
        )
    expected = _EXPECTED_BASE[folder_type]
    if not isinstance(plugin, expected):
        raise PluginLoadError(f"{manifest.name}: plugin must subclass {expected.__name__}")
    if plugin.plugin_id != manifest.name:
        raise PluginLoadError(
            f"plugin_id {plugin.plugin_id!r} does not match manifest name {manifest.name!r}"
        )

    plugin.initialize(context_builder(manifest, plugin))
    _mount_router(app, manifest, plugin, router_dependencies)
    names.add(manifest.name)
    loaded.append(LoadedPlugin(manifest=manifest, plugin=plugin, directory=plugin_dir))
    log.info("plugin %s loaded (%s)", manifest.name, manifest.type)


def _import_entry(plugin_name: str, entry_path: Path) -> ModuleType:
    """Import a plugin backend entry from a file path under a unique module name.

    The synthetic name (``wea_plugin_<name>``) avoids collisions between plugins
    that each ship a ``backend`` package and lets relative imports inside the
    package resolve.
    """
    if not entry_path.is_file():
        raise PluginLoadError(f"backend entry not found: {entry_path}")
    mod_name = f"wea_plugin_{plugin_name}"
    is_package = entry_path.name == "__init__.py"
    submodule_locations = [str(entry_path.parent)] if is_package else None
    spec = importlib.util.spec_from_file_location(
        mod_name, entry_path, submodule_search_locations=submodule_locations
    )
    if spec is None or spec.loader is None:
        raise PluginLoadError(f"cannot create an import spec for {entry_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module  # so relative imports during exec resolve
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(mod_name, None)
        raise
    return module


def _mount_router(
    app: FastAPI | None,
    manifest: Manifest,
    plugin: BasePlugin,
    router_dependencies: list[Any] | None,
) -> None:
    router = plugin.router()
    if router is None:
        return
    if manifest.frontend is None:
        log.warning(
            "plugin %s exposes routes but declares no frontend.route_base; not mounted",
            manifest.name,
        )
        return
    if app is not None:
        # route_base is the verbatim frontend path; the backend mounts at /api + it.
        # router_dependencies (auth) are applied to every route in the plugin router.
        app.include_router(
            router,
            prefix=f"/api{manifest.frontend.route_base}",
            tags=[f"Plugin: {manifest.name}"],
            dependencies=router_dependencies,
        )
