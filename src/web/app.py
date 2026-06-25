"""FastAPI application factory (1.B2).

Builds the web role: API routers + Swagger at /api/docs. At startup it creates
the schema idempotently and bootstraps the initial admin. Errors are rendered
with the `{detail, code}` envelope (BE-11).
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI

from src.core.bootstrap import ensure_initial_admin
from src.core.config import get_settings
from src.core.db import Base, create_schema, get_engine, init_engine, new_session
from src.core.feature_flags import clear_flags
from src.core.plugins.base import ScraperPlugin
from src.core.plugins.registry import load_plugins
from src.core.schema_drift import SchemaDriftItem, check_schema_drift
from src.core.scrape import implements_scraping
from src.web.deps import require_user
from src.web.error_handlers import register_error_handlers
from src.web.routers import (
    admin_scrapers,
    admin_system,
    admin_users,
    auth,
    catalog,
    health,
    me,
    plugins,
)
from src.web.routers.scrape import make_scrape_now_router
from src.web.spa import SpaStaticFiles

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# Built SPA baked into the web image (build-system.md); absent in dev/tests.
STATIC_DIR = Path(os.environ.get("WEA_STATIC_DIR", "/app/static"))


def create_app() -> FastAPI:
    settings = get_settings()
    init_engine(settings.core.database_url)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        create_schema()
        session = new_session()
        try:
            ensure_initial_admin(
                session,
                username=settings.admin_username,
                password=settings.admin_initial_password,
                locale=settings.core.default_locale,
            )
            # Dev feature flags are non-persistent: reset to defaults on each boot (4.B1a).
            clear_flags(session)
        finally:
            session.close()
        # Discover, load and mount the enabled plugins (REG-*). Isolated failures
        # are logged; the core stays up. Stored for the discovery endpoint. Every
        # plugin route sits behind authentication (#3).
        _app.state.loaded_plugins = load_plugins(_app, router_dependencies=[Depends(require_user)])
        # Schema-drift guard (4.B0): now that the schema is ensured (create_schema +
        # each plugin's initialize), compare the ORM model — core Base.metadata plus
        # every plugin's declared table_metadata — against the live DB. It ALWAYS runs
        # and logs warnings; WEA_SCHEMA_DRIFT_ALERT only gates the /api/health exposure
        # (health.py). A check failure must never block startup.
        metadatas = [Base.metadata] + [
            lp.plugin.table_metadata
            for lp in _app.state.loaded_plugins
            if lp.plugin.table_metadata is not None
        ]
        drift: list[SchemaDriftItem] = []
        try:
            drift = check_schema_drift(get_engine(), metadatas)
        except Exception:
            log.exception("schema-drift check failed")
        for item in drift:
            if item.missing_table:
                log.warning("schema drift: table %r is missing from the database", item.table)
            else:
                log.warning(
                    "schema drift: table %r is missing column(s): %s",
                    item.table,
                    ", ".join(item.missing_columns),
                )
        _app.state.schema_drift = drift
        # Standard per-scraper scrape-now routes (SCR-R15): mounted here in the web
        # (they need the authenticated user + a request session, so they cannot
        # live in the web-free core base) for every scraper that actually implements
        # run_for_user — a non-scraping test plugin gets no broken endpoint. The
        # handlers carry their own auth (UserDep).
        for lp in _app.state.loaded_plugins:
            if (
                isinstance(lp.plugin, ScraperPlugin)
                and lp.manifest.frontend is not None
                and implements_scraping(lp.plugin)
            ):
                _app.include_router(
                    make_scrape_now_router(lp),
                    prefix=f"/api{lp.manifest.frontend.route_base}",
                    tags=[f"Plugin: {lp.manifest.name}"],
                )
        # Mount the built SPA LAST (catch-all on "/"), after the core routers (added
        # at construction) and the plugin routers (added just above), so every /api
        # route — plugins included — takes precedence over the SPA fallback.
        if STATIC_DIR.is_dir():
            _app.mount("/", SpaStaticFiles(directory=STATIC_DIR, html=True), name="spa")
        log.info("web app started, version %s", settings.version)
        yield

    app = FastAPI(
        title="Watch 'Em All",
        version=settings.version,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    register_error_handlers(app)

    app.include_router(health.router, prefix="/api")
    app.include_router(auth.router, prefix="/api/auth")
    app.include_router(me.router, prefix="/api")
    app.include_router(admin_users.router, prefix="/api")
    app.include_router(admin_system.router, prefix="/api")
    app.include_router(admin_scrapers.router, prefix="/api")
    app.include_router(catalog.router, prefix="/api")
    app.include_router(plugins.router, prefix="/api")
    # The SPA catch-all is mounted in the lifespan, after the plugins (see above).

    return app


app = create_app()
