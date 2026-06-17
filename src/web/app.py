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

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.core.bootstrap import ensure_initial_admin
from src.core.config import get_settings
from src.core.db import create_schema, init_engine, new_session
from src.core.errors import APIError
from src.web.routers import auth, health, me
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

    @app.exception_handler(APIError)
    async def _api_error_handler(_request: Request, exc: APIError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code, content={"detail": exc.detail, "code": exc.code}
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error_handler(
        _request: Request, _exc: RequestValidationError
    ) -> JSONResponse:
        # api/README: validation errors are 400 with the {detail, code} envelope.
        return JSONResponse(
            status_code=400,
            content={"detail": "request validation failed", "code": "validation_error"},
        )

    app.include_router(health.router, prefix="/api")
    app.include_router(auth.router, prefix="/api/auth")
    app.include_router(me.router, prefix="/api")

    # Serve the built SPA last (catch-all) so /api routes take precedence.
    if STATIC_DIR.is_dir():
        app.mount("/", SpaStaticFiles(directory=STATIC_DIR, html=True), name="spa")

    return app


app = create_app()
