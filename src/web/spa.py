"""Serve the built SvelteKit SPA with a client-side-routing fallback.

The web image bakes the built bundle into WEA_STATIC_DIR (default /app/static).
A path that is neither an /api route nor a real file falls back to index.html so
deep links and client routes resolve. Absent in dev/tests (no built bundle), so
the app simply serves the API there.
"""

from __future__ import annotations

import posixpath

from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope


class SpaStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            # Fall back to the SPA only for client routes (no file extension); a
            # missing asset like /favicon.ico must stay a real 404, not text/html.
            if exc.status_code == 404 and not posixpath.splitext(path)[1]:
                return await super().get_response("index.html", scope)
            raise
