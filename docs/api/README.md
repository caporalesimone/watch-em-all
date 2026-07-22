# API — Conventions and Swagger

> Audience: developer, integrators.
>
> Limited to what is implemented (DOC-12). Full catalogue: [endpoints.md](endpoints.md).

## Conventions

- **Single `/api/` prefix** for all core endpoints; plugin routes live under `/api/plugins/{route_base}/…`. Everything else in the URL namespace belongs to the SPA (client-side fallback).
- **Authentication**: `Authorization: Bearer <access_token>`. Public endpoints: login, refresh, health.
- **Naming**: JSON in `snake_case` everywhere (including `expires_at`).
- **Types**: `Decimal` as a **string** (never float for prices), `datetime` ISO-8601 UTC, enums as strings.
- **Pagination**: `?page=&page_size=` with a `{items, total, page, page_size}` response on every potentially long list (catalog, and the histories/runs that arrive in later phases).
- **Errors**: `{detail, code}` with semantic statuses — `400` validation, `401` missing/expired token, `403` role or `must_change_password` (dedicated code), `404` not found / another user's, `409` state conflict, `429` rate limit.
- **Multi-tenancy**: every user endpoint operates implicitly on the token's user; another user's id answers `404` (never `403`, so existence is never revealed).

## Swagger / OpenAPI

FastAPI generates the OpenAPI schema automatically:

| URL | What |
|---|---|
| `/api/docs` | Swagger UI |
| `/api/redoc` | ReDoc |
| `/api/openapi.json` | OpenAPI 3 schema |

Every router declares `tags` (Auth, Me, Health, …) and request/response models are always Pydantic, so the schema is complete by construction. Plugin routers are included automatically, each documenting its own routes under a `Plugin: <name>` tag. Swagger UI is exposed in production too (hobby posture); endpoints stay protected by Bearer — the *Authorize* button takes the access token from a login.

## Versioning

No URL versioning in V1 (a single client on the same release). If cross-version compatibility ever becomes necessary, an `/api/v2/` prefix is the escape hatch ([future improvements](../future-improvements/README.md)).
