# API — Conventions and Swagger

> Audience: developer, integrators.
>
> English translation of the Italian reference [`docs-ita/api/README.md`](../../docs-ita/api/README.md), limited to what is implemented (DOC-12). Full catalogue: [endpoints.md](endpoints.md).

## Conventions

- **Single `/api/` prefix** for all core endpoints; plugin routes live under `/api/plugins/{route_base}/…`. Everything else in the URL namespace belongs to the SPA (client-side fallback).
- **Authentication**: `Authorization: Bearer <access_token>`. Public endpoints: login, refresh, health.
- **Naming**: JSON in `snake_case` everywhere (including `expires_at`).
- **Types**: `Decimal` as a **string** (never float for prices), `datetime` ISO-8601 UTC, enums as strings.
- **Errors**: `{detail, code}` with semantic statuses — `400` validation, `401` missing/expired token, `403` role or `must_change_password` (dedicated code), `404` not found / another user's, `409` state conflict, `429` rate limit.

## Swagger / OpenAPI

FastAPI generates the OpenAPI schema automatically:

| URL | What |
|---|---|
| `/api/docs` | Swagger UI |
| `/api/redoc` | ReDoc |
| `/api/openapi.json` | OpenAPI 3 schema |

Every router declares `tags` (Auth, Me, Health, …) and request/response models are always Pydantic, so the schema is complete by construction. Swagger UI is exposed in production too (hobby posture); endpoints stay protected by Bearer.
