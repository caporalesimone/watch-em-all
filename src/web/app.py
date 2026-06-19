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
from src.core.db import create_schema, init_engine, new_session
from src.core.plugins.registry import load_plugins
from src.web.deps import require_user
from src.web.error_handlers import register_error_handlers
from src.web.routers import admin_users, auth, catalog, health, me, plugins
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
        finally:
            session.close()
        # Discover, load and mount the enabled plugins (REG-*). Isolated failures
        # are logged; the core stays up. Stored for the discovery endpoint. Every
        # plugin route sits behind authentication (#3).
        _app.state.loaded_plugins = load_plugins(_app, router_dependencies=[Depends(require_user)])
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
    app.include_router(catalog.router, prefix="/api")
    app.include_router(plugins.router, prefix="/api")
    # The SPA catch-all is mounted in the lifespan, after the plugins (see above).

    return app


app = create_app()
