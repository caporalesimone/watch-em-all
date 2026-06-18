"""Exception handlers rendering the {detail, code} envelope (BE-11, api/README).

Kept out of app.py so it can be reused — and imported by tests — without
triggering app.py's module-level ``create_app()`` side effect.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.core.errors import APIError


def register_error_handlers(app: FastAPI) -> None:
    """Render APIError and validation errors with the {detail, code} envelope (BE-11)."""

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
