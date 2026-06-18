"""Tests for the plugin discovery API and icon serving (2.B4)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.db import init_engine
from src.core.plugins.registry import load_plugins
from src.web.error_handlers import register_error_handlers
from src.web.routers import plugins as plugins_router

_SCRAPER_BACKEND = """
from fastapi import APIRouter
from src.core.plugins.base import ScraperPlugin


class _Plugin(ScraperPlugin):
    plugin_id = "tp_scraper"

    def router(self):
        router = APIRouter()

        @router.get("/ping")
        def ping() -> dict[str, str]:
            return {"plugin": "tp_scraper"}

        return router


plugin = _Plugin()
"""

_NOTIFIER_BACKEND = """
from src.core.plugins.base import NotifierPlugin


class _Plugin(NotifierPlugin):
    plugin_id = "tp_notifier"


plugin = _Plugin()
"""

_ICON_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48"></svg>'


def _write_plugin(
    root: Path,
    folder: str,
    name: str,
    manifest: dict[str, Any],
    backend: str,
    *,
    icon: str | None = None,
) -> None:
    plugin_dir = root / folder / name
    (plugin_dir / "backend").mkdir(parents=True)
    (plugin_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (plugin_dir / "backend" / "__init__.py").write_text(backend, encoding="utf-8")
    if icon:
        (plugin_dir / icon).write_text(_ICON_SVG, encoding="utf-8")


def _build_app(tmp_path: Path) -> FastAPI:
    init_engine("sqlite+pysqlite:///:memory:")
    scraper_manifest: dict[str, Any] = {
        "name": "tp_scraper",
        "display_name": "TP Scraper",
        "type": "scraper",
        "version": "1.0.0",
        "api_version": 1,
        "enabled": True,
        "icon": "icon.svg",
        "backend": {"entry": "backend/__init__.py"},
        "frontend": {
            "entry": "frontend/index.ts",
            "route_base": "/plugins/tp-scraper",
            "i18n": "frontend/i18n",
        },
    }
    notifier_manifest: dict[str, Any] = {
        "name": "tp_notifier",
        "display_name": "TP Notifier",
        "type": "notifier",
        "version": "1.0.0",
        "api_version": 1,
        "enabled": True,
        "backend": {"entry": "backend/__init__.py"},
    }
    _write_plugin(
        tmp_path, "scrapers", "tp_scraper", scraper_manifest, _SCRAPER_BACKEND, icon="icon.svg"
    )
    _write_plugin(tmp_path, "notifiers", "tp_notifier", notifier_manifest, _NOTIFIER_BACKEND)

    app = FastAPI()
    register_error_handlers(app)
    app.include_router(plugins_router.router, prefix="/api")
    app.state.loaded_plugins = load_plugins(app, plugins_root=tmp_path)
    return app


def test_discovery_lists_plugins_with_route_and_icon(tmp_path: Path) -> None:
    app = _build_app(tmp_path)
    with TestClient(app) as client:
        data = client.get("/api/plugins").json()
        by_name = {p["name"]: p for p in data}
        assert set(by_name) == {"tp_scraper", "tp_notifier"}

        scraper = by_name["tp_scraper"]
        assert scraper["type"] == "scraper"
        assert scraper["route_base"] == "/plugins/tp-scraper"
        assert scraper["icon"] == "/api/plugin-assets/tp_scraper/icon"
        assert scraper["display_name"] == "TP Scraper"
        # No internal paths leak (REG-R6): exactly the contract fields.
        assert set(scraper) == {"name", "type", "route_base", "icon", "display_name"}

        notifier = by_name["tp_notifier"]
        assert notifier["type"] == "notifier"
        assert notifier["route_base"] is None
        assert notifier["icon"] is None


def test_plugin_route_mounted_and_in_openapi(tmp_path: Path) -> None:
    app = _build_app(tmp_path)
    with TestClient(app) as client:
        resp = client.get("/api/plugins/tp-scraper/ping")
        assert resp.status_code == 200
        assert resp.json() == {"plugin": "tp_scraper"}

        schema = client.get("/openapi.json").json()
        assert "/api/plugins/tp-scraper/ping" in schema["paths"]
        operation = schema["paths"]["/api/plugins/tp-scraper/ping"]["get"]
        assert "Plugin: tp_scraper" in operation.get("tags", [])


def test_icon_served_and_unknown_is_404(tmp_path: Path) -> None:
    app = _build_app(tmp_path)
    with TestClient(app) as client:
        icon = client.get("/api/plugin-assets/tp_scraper/icon")
        assert icon.status_code == 200
        assert icon.headers["content-type"].startswith("image/svg")

        missing = client.get("/api/plugin-assets/nope/icon")
        assert missing.status_code == 404
        assert missing.json()["code"] == "not_found"


def test_discovery_endpoint_wired_on_real_app(client: TestClient) -> None:
    resp = client.get("/api/plugins")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
