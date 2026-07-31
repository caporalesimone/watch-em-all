"""The database-incompatibility page (INC-R1..R4).

When the schema-drift guard (4.B0) finds that the running code and the database do not
agree, the application does not pretend to work and does not refuse to start either:
**it starts, and every page says what is wrong**.

Refusing to start was the other candidate and is worse for the person who has to fix
it. A container that exits leaves nothing to read but `docker logs`, and on a restart
policy it exits in a loop; the operator sees a dead service and has to go digging for
the reason. A container that stays up can *explain itself* — which tables disagree,
which version is running, and what to do about it — at the same URL they already had
open. The failure is not intermittent, so there is no risk of the message being stale.

What it replaces matters too. Without this, a mismatched database surfaces as a
scattering of HTTP 500s at whatever page happens to touch the wrong table first, with
the real cause in a startup log nobody re-reads: three symptoms and one hidden reason.

The page is deliberately **self-contained** — inline CSS, no asset, no template engine,
no i18n lookup. It has to render when the database is unusable, and anything it had to
fetch first would be one more thing that can fail at the worst moment. It is
operator-facing, so it stays in English like the logs.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from html import escape

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.responses import Response

from src.core.schema_drift import SchemaDriftItem

# Kept reachable while the rest is blocked: it is what a monitor polls and what an
# operator curls, and it already reports the drift itself. Blocking it would turn a
# legible failure into an unreachable service, which is the thing this page exists to
# avoid (INC-R3).
_ALWAYS_ALLOWED = ("/api/health",)

_STATUS = 503  # Service Unavailable: true, and it keeps monitors from reading this as OK.

_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Watch 'Em All — database incompatible</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
         line-height: 1.5; margin: 0; padding: 2rem 1.25rem;
         background: #f8fafc; color: #0f172a; }}
  main {{ max-width: 44rem; margin: 0 auto; }}
  h1 {{ font-size: 1.35rem; margin: 0 0 .35rem; }}
  p {{ margin: .6rem 0; }}
  .sub {{ color: #475569; margin-top: 0; }}
  ul {{ background: #fff; border: 1px solid #e2e8f0; border-radius: .5rem;
        padding: .85rem 1.25rem; margin: 1.1rem 0; }}
  li {{ margin: .3rem 0; font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
        font-size: .875rem; }}
  code {{ background: #e2e8f0; border-radius: .25rem; padding: .1rem .35rem;
          font-size: .875rem; }}
  footer {{ color: #64748b; font-size: .8rem; margin-top: 1.5rem; }}
  @media (prefers-color-scheme: dark) {{
    body {{ background: #0f172a; color: #e2e8f0; }}
    .sub {{ color: #94a3b8; }}
    ul {{ background: #1e293b; border-color: #334155; }}
    code {{ background: #334155; }}
    footer {{ color: #94a3b8; }}
  }}
</style></head>
<body><main>
  <h1>👀 This database does not match this version</h1>
  <p class="sub">Watch 'Em All started, but it will not read or write anything until the
  two agree — working half-way would corrupt what is already there.</p>
  <p>The schema the running code expects differs from the schema in the database:</p>
  <ul>{findings}</ul>
  <p><strong>Before version 1.0 the schema is not migrated.</strong> The intended fix is to
  recreate the database — on a development or pre-production setup:</p>
  <p><code>docker compose -f compose-dev.yml down -v</code>,
  then <code>up -d</code> again</p>
  <p>If the data matters, restore a backup taken with the version you were running before,
  or go back to that version: nothing here has been modified.</p>
  <footer>Running version {version} · this page is served in place of every page and API
  route while the mismatch lasts; <code>/api/health</code> stays available.</footer>
</main></body></html>
"""


def render_page(drift: list[SchemaDriftItem], version: str) -> str:
    """The page for these findings. Everything interpolated is escaped: a table or column
    name comes from a database this process does not control."""
    findings = "".join(f"<li>{escape(item.summary())}</li>" for item in drift)
    return _PAGE.format(findings=findings, version=escape(version))


def install_incompatibility_gate(app: FastAPI, version: str) -> None:
    """Serve the incompatibility page instead of the application while drift is present.

    Reads ``app.state.schema_drift``, which the lifespan fills **before** the first
    request is served, so there is no window in which a mismatched database is reachable.
    An empty list — the normal case — costs one attribute read per request.

    An API route answers JSON, not HTML: the SPA and any script talking to this instance
    get a machine-readable ``schema_incompatible`` instead of a page they cannot parse
    (INC-R2).
    """

    @app.middleware("http")
    async def _gate(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        drift: list[SchemaDriftItem] = getattr(request.app.state, "schema_drift", [])
        if not drift or request.url.path in _ALWAYS_ALLOWED:
            return await call_next(request)
        if request.url.path.startswith("/api/"):
            return JSONResponse(
                status_code=_STATUS,
                content={
                    "code": "schema_incompatible",
                    "detail": "the database schema does not match this version of the application",
                    "findings": [item.summary() for item in drift],
                    "version": version,
                },
            )
        return HTMLResponse(status_code=_STATUS, content=render_page(drift, version))
