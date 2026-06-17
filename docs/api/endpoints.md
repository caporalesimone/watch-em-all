# API — Endpoint catalogue

> The single, canonical reference of the core HTTP endpoints. Conventions and Swagger: [README.md](README.md).
>
> English translation of the Italian reference [`docs-ita/api/endpoints.md`](../../docs-ita/api/endpoints.md), limited to what is implemented (DOC-12). Phase 1 ships Auth, Me and Health; catalog, carts, history, alerts, notifiers and admin endpoints arrive in later phases.

Role legend: 🌐 public · 👤 user · 🛡 admin

## Auth — [auth](../4-capabilities/core/auth.md)

| Method | Path | Role | Body | Response | Notes |
|---|---|---|---|---|---|
| POST | `/api/auth/login` | 🌐 | `{username, password}` | `{access_token, refresh_token, expires_at}` | rate-limited; `expires_at` = access expiry |
| POST | `/api/auth/refresh` | 🌐 | `{refresh_token}` | new pair | jti rotation; reuse → 401 + global invalidation |
| POST | `/api/auth/logout` | 👤🛡 | — | 204 | token_version += 1 (all devices) |
| POST | `/api/auth/change-password` | 👤🛡 | `{old_password?, new_password}` | 204 | `old_password` required for a **normal** change, omitted for the **forced** one (must_change_password); clears the flag; invalidates tokens |

## Profile (Me)

| Method | Path | Role | Body | Response | Notes |
|---|---|---|---|---|---|
| GET | `/api/me` | 👤🛡 | — | `{id, username, first_name, last_name, role, locale, must_change_password}` | exempt from the must_change_password gate (drives the SPA boot) |
| PATCH | `/api/me` | 👤🛡 | `{locale?}` | 200 | V1 English-only: the only accepted value is `en` |

## Health — [deployment](../infrastructure/deployment.md)

| Method | Path | Role | Response | Notes |
|---|---|---|---|---|
| GET | `/api/health` | 🌐 | `200 {status, db, version, worker_heartbeat_age_s}` / `503` | app alive + DB reachable; `version` is the baked product version; `worker_heartbeat_age_s` is `null` until the worker persists its heartbeat (phase 4) |
