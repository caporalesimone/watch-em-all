"""TP Scraper — a throwaway Test Plugin (phase 2 only).

It exercises the plugin backbone end-to-end: a manifest-described scraper that, at
load, creates its OWN table (isolated MetaData) and registers a route under
/api/plugins/tp-scraper. It does NOT scrape anything — the real scraper contract
(run_for_user, config schemas, ...) arrives in later phases. Delete this folder
once a real scraper exists.
"""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from src.core.plugins.base import ScraperPlugin
from src.core.plugins.context import PluginContext


class _Base(DeclarativeBase):
    """The plugin's own metadata, separate from the core schema (CTX-R6)."""


class Ping(_Base):
    __tablename__ = "plugin_tp_scraper_pings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    note: Mapped[str] = mapped_column(String(64), nullable=False, default="hello")


class TpScraperPlugin(ScraperPlugin):
    plugin_id = "tp_scraper"

    def initialize(self, context: PluginContext) -> None:
        # Idempotently create the plugin's own table through the context engine.
        _Base.metadata.create_all(context.engine)
        context.logger.info("tp_scraper initialized; own table ensured")

    def router(self) -> APIRouter:
        router = APIRouter()

        @router.get("/ping")
        def ping() -> dict[str, str]:
            return {"plugin": "tp_scraper", "status": "ok"}

        return router


plugin = TpScraperPlugin()
