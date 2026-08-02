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
from src.core.feature_flags import clear_flags, effective_flags
from src.core.plugins.base import ScraperPlugin
from src.core.plugins.registry import load_plugins
from src.core.schema_drift import SchemaDriftItem, check_schema_drift
from src.core.scrape import implements_scraping
from src.core.system_log import install_system_log_handler
from src.web.adjust import register_notifiers, register_scrapers
from src.web.deps import require_user
from src.web.error_handlers import register_error_handlers
from src.web.incompatible import install_incompatibility_gate
from src.web.jobs import reclaim_orphans, start_drainers, stop_drainers
from src.web.routers import (
    admin_dashboard,
    admin_message_templates,
    admin_messages,
    admin_notifiers,
    admin_runs,
    admin_scrapers,
    admin_system,
    admin_users,
    alerts,
    auth,
    carts,
    catalog,
    health,
    me,
    notifiers,
    plugins,
    products,
)
from src.web.routers.scrape import make_scrape_now_router
from src.web.spa import SpaStaticFiles

logging.basicConfig(level=logging.INFO)
# `wea.web`, not `__name__`: this module logs the process's lifecycle (startup, shutdown) and
# its boot checks (feature flags, schema drift) — the same events the worker already persists
# to `system_log` under `worker`. The name is what opts them in (system_log._source_for); the
# rest of the web, per-request logs included, keeps `__name__` and stays on stdout (LOG-R1).
log = logging.getLogger("wea.web")

# Built SPA baked into the web image (build-system.md); absent in dev/tests.
STATIC_DIR = Path(os.environ.get("WEA_STATIC_DIR", "/app/static"))


def create_app() -> FastAPI:
    settings = get_settings()
    init_engine(settings.core.database_url)
    # Scraper events that run in the web process (manual scrape-now) reach system_log too.
    install_system_log_handler()

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
            log.info("feature flags: %s", effective_flags(session))
        finally:
            session.close()
        # Discover, load and mount the enabled plugins (REG-*). Isolated failures
        # are logged; the core stays up. Stored for the discovery endpoint. Every
        # plugin route sits behind authentication (#3).
        _app.state.loaded_plugins = load_plugins(_app, router_dependencies=[Depends(require_user)])
        # Cache the loaded scrapers so the event-driven alert run (after a manual scrape)
        # can bind each cart's adjustments without a request (adjust.run_user_alerts).
        register_scrapers(_app.state.loaded_plugins)
        # Cache the loaded notifiers so the event-driven alert run enqueues per-channel
        # deliveries (phase 7); the worker drains the pending ones.
        register_notifiers(_app.state.loaded_plugins)
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
            log.error("schema drift: %s", item.summary())
        if drift:
            # Logged as an error, not a warning, and said once in one line: from here on
            # every page and every API route answers with the incompatibility instead of
            # the application (INC-R1), so this is the only place the reason is written.
            log.error(
                "database incompatible with version %s — serving the incompatibility page "
                "on every route except /api/health; nothing will be read or written",
                settings.version,
            )
        # Filled before the first request is served, which is what makes the gate
        # airtight: there is no window in which a mismatched database is reachable.
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
        # Jobs that resolve a newly added watch run here, one drainer per scraper (9.X6c).
        # Reclaim first: they live in this process, so anything still marked running was
        # left by the process that died, and that state blocks the user's next submission.
        reclaim_orphans(_app.state.loaded_plugins)
        start_drainers(_app.state.loaded_plugins)
        log.info("web started, version %s", settings.version)
        try:
            yield
        finally:
            stop_drainers()
            # Uvicorn runs the shutdown half of the lifespan on SIGTERM/SIGINT, so this is
            # the line that says the container went down on purpose. In a `finally` because
            # a crash on the way out is exactly when we want the record.
            log.info("web stopped")

    app = FastAPI(
        title="Watch 'Em All",
        version=settings.version,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    register_error_handlers(app)
    # Before every route, including the SPA's catch-all: while the database does not match
    # this version, the answer is the incompatibility page rather than a scattering of 500s
    # from whichever page touches the wrong table first (INC-R1).
    install_incompatibility_gate(app, settings.version)

    app.include_router(health.router, prefix="/api")
    app.include_router(auth.router, prefix="/api/auth")
    app.include_router(me.router, prefix="/api")
    app.include_router(admin_users.router, prefix="/api")
    app.include_router(admin_system.router, prefix="/api")
    app.include_router(admin_scrapers.router, prefix="/api")
    app.include_router(admin_runs.router, prefix="/api")
    app.include_router(admin_dashboard.router, prefix="/api")
    app.include_router(admin_notifiers.router, prefix="/api")
    app.include_router(admin_messages.router, prefix="/api")
    app.include_router(admin_message_templates.router, prefix="/api")
    app.include_router(catalog.router, prefix="/api")
    app.include_router(products.router, prefix="/api")
    app.include_router(carts.router, prefix="/api")
    app.include_router(alerts.router, prefix="/api")
    app.include_router(notifiers.router, prefix="/api")
    app.include_router(plugins.router, prefix="/api")
    # The SPA catch-all is mounted in the lifespan, after the plugins (see above).

    return app


app = create_app()
