"""Tests for the plugin registry: load, isolation and routing (2.B2)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.core.plugins.base import BasePlugin
from src.core.plugins.context import PluginContext
from src.core.plugins.manifest import Manifest
from src.core.plugins.registry import load_plugins

# A minimal scraper backend that exports `plugin` and a /ping route.
_SCRAPER_BACKEND = """
from fastapi import APIRouter
from src.core.plugins.base import ScraperPlugin


class _Plugin(ScraperPlugin):
    plugin_id = "{plugin_id}"

    def router(self):
        router = APIRouter()

        @router.get("/ping")
        def ping() -> dict[str, str]:
            return {{"plugin": "{plugin_id}"}}

        return router


plugin = _Plugin()
"""

# A minimal notifier backend: no UI, no routes.
_NOTIFIER_BACKEND = """
from src.core.plugins.base import NotifierPlugin


class _Plugin(NotifierPlugin):
    plugin_id = "{plugin_id}"


plugin = _Plugin()
"""

_engine = create_engine("sqlite+pysqlite:///:memory:")


def _ctx_builder(manifest: Manifest, plugin: BasePlugin) -> PluginContext:
    return PluginContext(
        engine=_engine,
        db=Session(_engine),
        logger=logging.getLogger(f"plugin.{manifest.name}"),
        config={},
    )


def _manifest(
    name: str, plugin_type: str, *, enabled: bool = True, with_frontend: bool = True
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "name": name,
        "display_name": name.replace("_", " ").title(),
        "type": plugin_type,
        "version": "1.0.0",
        "api_version": 1,
        "enabled": enabled,
        "backend": {"entry": "backend/__init__.py"},
    }
    if with_frontend:
        data["frontend"] = {
            "entry": "frontend/index.ts",
            "route_base": f"/plugins/{name.replace('_', '-')}",
            "i18n": "frontend/i18n",
        }
    return data


def _scaffold(
    root: Path, folder: str, name: str, *, manifest: dict[str, Any], backend: str
) -> None:
    plugin_dir = root / folder / name
    (plugin_dir / "backend").mkdir(parents=True)
    (plugin_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (plugin_dir / "backend" / "__init__.py").write_text(backend, encoding="utf-8")


def _make_scraper(
    root: Path,
    name: str,
    *,
    enabled: bool = True,
    backend: str | None = None,
    manifest_overrides: dict[str, Any] | None = None,
) -> None:
    manifest = _manifest(name, "scraper", enabled=enabled)
    if manifest_overrides:
        manifest.update(manifest_overrides)
    src = backend if backend is not None else _SCRAPER_BACKEND.format(plugin_id=name)
    _scaffold(root, "scrapers", name, manifest=manifest, backend=src)


def _names(loaded: list[Any]) -> list[str]:
    return [lp.manifest.name for lp in loaded]


def test_loads_enabled_scraper_and_mounts_router(tmp_path: Path) -> None:
    _make_scraper(tmp_path, "tp_scraper")
    app = FastAPI()
    loaded = load_plugins(app, context_builder=_ctx_builder, plugins_root=tmp_path)
    assert _names(loaded) == ["tp_scraper"]
    with TestClient(app) as client:
        resp = client.get("/api/plugins/tp-scraper/ping")
        assert resp.status_code == 200
        assert resp.json() == {"plugin": "tp_scraper"}


def test_skips_disabled_plugin(tmp_path: Path) -> None:
    _make_scraper(tmp_path, "tp_scraper", enabled=False)
    app = FastAPI()
    loaded = load_plugins(app, context_builder=_ctx_builder, plugins_root=tmp_path)
    assert loaded == []
    with TestClient(app) as client:
        assert client.get("/api/plugins/tp-scraper/ping").status_code == 404


def test_broken_manifest_rejected_others_survive(tmp_path: Path) -> None:
    _make_scraper(tmp_path, "broken_one", manifest_overrides={"api_version": 999})
    _make_scraper(tmp_path, "good_one")
    app = FastAPI()
    loaded = load_plugins(app, context_builder=_ctx_builder, plugins_root=tmp_path)
    assert _names(loaded) == ["good_one"]


def test_import_error_rejected_others_survive(tmp_path: Path) -> None:
    _make_scraper(tmp_path, "boom", backend="raise RuntimeError('boom at import')")
    _make_scraper(tmp_path, "good_one")
    app = FastAPI()
    loaded = load_plugins(app, context_builder=_ctx_builder, plugins_root=tmp_path)
    assert _names(loaded) == ["good_one"]


def test_plugin_id_mismatch_rejected(tmp_path: Path) -> None:
    _make_scraper(tmp_path, "tp_scraper", backend=_SCRAPER_BACKEND.format(plugin_id="different_id"))
    app = FastAPI()
    loaded = load_plugins(app, context_builder=_ctx_builder, plugins_root=tmp_path)
    assert loaded == []


def test_wrong_base_class_rejected(tmp_path: Path) -> None:
    # A scraper folder whose plugin subclasses NotifierPlugin instead.
    _make_scraper(tmp_path, "tp_scraper", backend=_NOTIFIER_BACKEND.format(plugin_id="tp_scraper"))
    app = FastAPI()
    loaded = load_plugins(app, context_builder=_ctx_builder, plugins_root=tmp_path)
    assert loaded == []


def test_duplicate_name_rejected(tmp_path: Path) -> None:
    _make_scraper(tmp_path, "dup")
    notifier = _manifest("dup", "notifier", with_frontend=False)
    _scaffold(
        tmp_path,
        "notifiers",
        "dup",
        manifest=notifier,
        backend=_NOTIFIER_BACKEND.format(plugin_id="dup"),
    )
    app = FastAPI()
    loaded = load_plugins(app, context_builder=_ctx_builder, plugins_root=tmp_path)
    # The scraper folder loads first; the notifier with the same name is rejected.
    assert _names(loaded) == ["dup"]
    assert loaded[0].manifest.type == "scraper"


def test_loads_notifier_without_router(tmp_path: Path) -> None:
    notifier = _manifest("tp_notifier", "notifier", with_frontend=False)
    _scaffold(
        tmp_path,
        "notifiers",
        "tp_notifier",
        manifest=notifier,
        backend=_NOTIFIER_BACKEND.format(plugin_id="tp_notifier"),
    )
    app = FastAPI()
    loaded = load_plugins(app, context_builder=_ctx_builder, plugins_root=tmp_path)
    assert _names(loaded) == ["tp_notifier"]
    assert loaded[0].manifest.type == "notifier"
    paths = [getattr(route, "path", "") for route in app.routes]
    assert all(not path.startswith("/api/plugins") for path in paths)
