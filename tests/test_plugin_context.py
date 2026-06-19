"""Tests for the Plugin Context factory and table ownership (2.B3)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from sqlalchemy import inspect, select

from src.core.contracts import Product
from src.core.db import create_schema, get_engine, init_engine, new_session
from src.core.models import CatalogProduct
from src.core.plugins.base import NotifierPlugin, ScraperPlugin
from src.core.plugins.context import build_context
from src.core.plugins.manifest import Manifest
from src.core.plugins.registry import load_plugins

# A scraper whose initialize() creates its own table through the context engine.
_CTX_SCRAPER_BACKEND = """
from sqlalchemy import Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from src.core.plugins.base import ScraperPlugin


class _Base(DeclarativeBase):  # the plugin's OWN MetaData, separate from the core
    pass


class _Item(_Base):
    __tablename__ = "plugin_tp_ctx_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50))


class _Plugin(ScraperPlugin):
    plugin_id = "tp_ctx"

    def identity_seed(self, raw):
        return None

    def initialize(self, ctx):
        _Base.metadata.create_all(ctx.engine)
        ctx.logger.info("tp_ctx initialized")


plugin = _Plugin()
"""


def _scaffold_scraper(root: Path, name: str, backend: str) -> None:
    plugin_dir = root / "scrapers" / name
    (plugin_dir / "backend").mkdir(parents=True)
    manifest: dict[str, Any] = {
        "name": name,
        "display_name": "TP Ctx",
        "type": "scraper",
        "version": "1.0.0",
        "api_version": 1,
        "enabled": True,
        "backend": {"entry": "backend/__init__.py"},
        "frontend": {
            "entry": "frontend/index.ts",
            "route_base": f"/plugins/{name.replace('_', '-')}",
            "i18n": "frontend/i18n",
        },
    }
    (plugin_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (plugin_dir / "backend" / "__init__.py").write_text(backend, encoding="utf-8")


def test_plugin_creates_its_own_table_in_initialize(tmp_path: Path) -> None:
    init_engine("sqlite+pysqlite:///:memory:")
    _scaffold_scraper(tmp_path, "tp_ctx", _CTX_SCRAPER_BACKEND)
    app = FastAPI()
    loaded = load_plugins(app, plugins_root=tmp_path)  # default build_context
    assert [lp.manifest.name for lp in loaded] == ["tp_ctx"]
    assert "plugin_tp_ctx_items" in inspect(get_engine()).get_table_names()


def test_build_context_shape() -> None:
    init_engine("sqlite+pysqlite:///:memory:")
    manifest = Manifest.model_validate(
        {
            "name": "tp_notifier",
            "display_name": "TP Notifier",
            "type": "notifier",
            "version": "1.0.0",
            "api_version": 1,
            "enabled": True,
            "backend": {"entry": "backend/__init__.py"},
        }
    )

    class _Dummy(NotifierPlugin):
        plugin_id = "tp_notifier"

    ctx = build_context(manifest, _Dummy())
    assert ctx.config == {}
    assert ctx.engine is get_engine()
    assert "tp_notifier" in ctx.logger.name
    assert callable(ctx.update_catalog)


def test_update_catalog_binding_writes_through_service() -> None:
    """The bound callback delivers products to the Catalog Update Service under
    this context's session and the plugin's plugin_id (the only write path)."""
    init_engine("sqlite+pysqlite:///:memory:")
    create_schema()
    manifest = Manifest.model_validate(
        {
            "name": "dragon_store",
            "display_name": "Dragon Store",
            "type": "scraper",
            "version": "1.0.0",
            "api_version": 1,
            "enabled": True,
            "backend": {"entry": "backend/__init__.py"},
        }
    )

    class _Scraper(ScraperPlugin):
        plugin_id = "dragon_store"

        def identity_seed(self, raw: object) -> str | None:
            return None

    ctx = build_context(manifest, _Scraper())
    product = Product(
        plugin_id="dragon_store",
        external_id="abc123",
        url="https://example.com/p.gp.35880.uw",
        name="Necronomicon",
        price_current=Decimal("40.00"),
        is_available=True,
        scraped_at=datetime.now(UTC),
    )

    counters = ctx.update_catalog(7, [product])

    assert counters.new == 1
    row = new_session().scalar(select(CatalogProduct).where(CatalogProduct.user_id == 7))
    assert row is not None
    assert row.plugin_id == "dragon_store"
    assert row.external_id == "abc123"
