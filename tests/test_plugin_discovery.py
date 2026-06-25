"""Tests for the plugin discovery API and icon serving (2.B4)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.db import init_engine
from src.core.plugins.registry import load_plugins
from src.web.deps import require_user
from src.web.error_handlers import register_error_handlers
from src.web.routers import plugins as plugins_router

_SCRAPER_BACKEND = """
from fastapi import APIRouter
from src.core.plugins.base import ScraperPlugin


class _Plugin(ScraperPlugin):
    plugin_id = "tp_scraper"

    def identity_seed(self, raw):
        return None

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
    # The discovery endpoint is auth-gated (#3); bypass it for these unit tests
    # (the real-app gating is checked in test_discovery_endpoint_wired_on_real_app).
    app.dependency_overrides[require_user] = lambda: None
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
        assert scraper["version"] == "1.0.0"  # 4.B0a: manifest version exposed
        # No internal paths leak (REG-R6): exactly the contract fields.
        assert set(scraper) == {"name", "type", "route_base", "icon", "display_name", "version"}

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


def test_icon_convention_prefers_ico_over_svg(tmp_path: Path) -> None:
    # No manifest.icon: the registry auto-detects frontend/assets/plugin-icon.{ico,svg},
    # preferring .ico.
    init_engine("sqlite+pysqlite:///:memory:")
    manifest: dict[str, Any] = {
        "name": "tp_scraper",
        "display_name": "TP Scraper",
        "type": "scraper",
        "version": "1.0.0",
        "api_version": 1,
        "enabled": True,
        "backend": {"entry": "backend/__init__.py"},
        "frontend": {
            "entry": "frontend/index.ts",
            "route_base": "/plugins/tp-scraper",
            "i18n": "frontend/i18n",
        },
    }
    _write_plugin(tmp_path, "scrapers", "tp_scraper", manifest, _SCRAPER_BACKEND)
    assets = tmp_path / "scrapers" / "tp_scraper" / "frontend" / "assets"
    assets.mkdir(parents=True)
    (assets / "plugin-icon.svg").write_text(_ICON_SVG, encoding="utf-8")
    (assets / "plugin-icon.ico").write_bytes(b"\x00\x00\x01\x00")

    app = FastAPI()
    register_error_handlers(app)
    app.include_router(plugins_router.router, prefix="/api")
    app.dependency_overrides[require_user] = lambda: None
    app.state.loaded_plugins = load_plugins(app, plugins_root=tmp_path)

    with TestClient(app) as client:
        by_name = {p["name"]: p for p in client.get("/api/plugins").json()}
        assert by_name["tp_scraper"]["icon"] == "/api/plugin-assets/tp_scraper/icon"
        icon = client.get("/api/plugin-assets/tp_scraper/icon")
        assert icon.status_code == 200
        assert icon.headers["content-type"] == "image/x-icon"  # .ico preferred over .svg


def test_discovery_endpoint_wired_on_real_app(client: TestClient) -> None:
    # Discovery is behind auth (#3): an unauthenticated request is rejected.
    resp = client.get("/api/plugins")
    assert resp.status_code == 401


def test_spa_catch_all_mounted_last_so_api_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Regression: the SPA is a catch-all on "/"; if it is mounted before the plugin
    # routers (added in the lifespan), it shadows /api/plugins/<route>/... and serves
    # index.html instead. It must be the LAST route. (Only reproducible with the SPA
    # mounted, i.e. with a static dir present — which the other tests don't have.)
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<!doctype html><title>spa</title>", encoding="utf-8")

    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        'core:\n  database_url: "sqlite+pysqlite:///:memory:"\n'
        '  secret_key: "${WEA_SECRET_KEY}"\n  default_locale: "en"\n'
        "  access_token_ttl_min: 15\n  refresh_token_ttl_days: 7\n",
        encoding="utf-8",
    )
    ver = tmp_path / "VERSION"
    ver.write_text("9.9.9-test\n", encoding="utf-8")
    monkeypatch.setenv("WEA_SECRET_KEY", "x" * 64)
    monkeypatch.setenv("WEA_ADMIN_INITIAL_USERNAME", "admin")
    monkeypatch.setenv("WEA_ADMIN_INITIAL_PASSWORD", "initpass123")

    from src.core import config as config_mod

    monkeypatch.setattr(config_mod, "CONFIG_PATH", str(cfg))
    monkeypatch.setattr(config_mod, "VERSION_PATH", str(ver))
    config_mod.get_settings.cache_clear()

    from src.web import app as app_mod

    monkeypatch.setattr(app_mod, "STATIC_DIR", static)

    app = app_mod.create_app()
    with TestClient(app) as test_client:
        assert getattr(app.router.routes[-1], "name", None) == "spa"
        assert test_client.get("/api/health").status_code == 200  # core /api still wins
        assert "<!doctype html>" in test_client.get("/").text.lower()  # SPA served at root
    config_mod.get_settings.cache_clear()
