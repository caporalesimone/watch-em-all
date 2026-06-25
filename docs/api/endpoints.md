# API — Endpoint catalogue

> The single, canonical reference of the core HTTP endpoints. Conventions and Swagger: [README.md](README.md).
>
> English translation of the Italian reference [`docs-ita/api/endpoints.md`](../../docs-ita/api/endpoints.md), limited to what is implemented (DOC-12). Phase 1 ships Auth, Me and Health; phase 3 adds admin user management, plugin discovery, the read-only **catalog** and the scraper plugin's own routes; carts, history, alerts, notifiers and scheduling arrive in later phases.

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

## Admin — users — [user-management](../3-features/admin/user-management.md)

| Method | Path | Role | Body | Notes |
|---|---|---|---|---|
| POST | `/api/admin/users` | 🛡 | `{username, first_name, last_name, role, temp_password}` | creates an account with a forced first-login password change; duplicate username → 409 (USR-R1/R2/R15) |
| GET | `/api/admin/users` | 🛡 | — | lists all accounts (username, name, role, status, last login) |

## Admin — system

| Method | Path | Role | Response | Notes |
|---|---|---|---|---|
| GET | `/api/admin/errors` | 🛡 | `[{source, type, title, description}]` | **admin-only** feed of errors/warnings (admin diagnostics), kept off the public `/api/health` probe. First source: schema drift (4.B0), behind `WEA_SCHEMA_DRIFT_ALERT` |
| GET | `/api/admin/feature-flags` | 🛡 | `{key: {…}}` | dev feature flags, effective values (defaults + overrides). Admin-only (4.B1a) |
| PATCH | `/api/admin/feature-flags` | 🛡 | `{key: {…}}` | set one or more flags (known keys only); returns the effective map. Non-persistent — reset at web startup |

Known flags (params shown with their defaults): `worker_tick` `{seconds: 60}` (worker dispatcher tick); `scrape_now_cooldown` `{seconds: 3600}` (manual scrape-now cooldown — lower it, e.g. `30`, to exercise the countdown without waiting the hour).

## Admin — scrapers — [scraper-scheduling-and-limits](../3-features/admin/scraper-scheduling-and-limits.md)

| Method | Path | Role | Response | Notes |
|---|---|---|---|---|
| GET | `/api/admin/scrapers` | 🛡 | `[{scraper_id, display_name, times, enabled, last_slot}]` | schedulable scrapers (those that implement scraping) + their schedule (4.B2) |
| PUT | `/api/admin/scrapers/{scraper_id}` | 🛡 | `{times, enabled}` → the updated schedule | set the slots (`"HH:MM"` or `"HH:MM:SS"`, de-duplicated/sorted; **422** on a bad time) and the enabled flag; unknown scraper → **404** |

## Plugin discovery — [plugin-registry](../4-capabilities/core/plugin-registry.md)

| Method | Path | Role | Response | Notes |
|---|---|---|---|---|
| GET | `/api/plugins` | 👤🛡 | `[{name, type, route_base, icon, display_name, version}]` | only enabled + loaded plugins; no internal paths. `route_base`/`icon` are `null` for a plugin without a frontend (notifiers); `version` is the plugin's own manifest version (4.B0a) |
| GET | `/api/plugin-assets/{name}/icon` | 🌐 | image | the plugin's manifest `icon`, served as a static asset (path-traversal guarded); 404 if absent. Public like the SPA bundle — the browser loads it as an `<img>`, which cannot carry the bearer token |

Plugin-specific routes are registered by each plugin under `/api{route_base}` (e.g. `/api/plugins/my-store/...`), **behind authentication** (the registry applies a user dependency to every plugin router), and documented in OpenAPI under the `Plugin: <name>` tag.

## Catalog — [catalog-update-service](../4-capabilities/core/catalog-update-service.md)

| Method | Path | Role | Query | Notes |
|---|---|---|---|---|
| GET | `/api/catalog` | 👤 | `?page=&page_size=&sort=&order=&q=&available=&removed=` | the current user's catalog as the Product Picker table: paginated server-side, returns `{items, total, page, page_size}`. `sort` ∈ {`name`, `plugin_id`, `price_current`, `price_original`, `is_available`, `last_seen_at`} (default `last_seen_at`); `order` `asc`\|`desc`; `q` = case-insensitive name search; `available`/`removed` = optional boolean filters |

The catalog is **read-only** here: it is written only through the Catalog Update Service (a scrape). The cleanup/mutation endpoints (remove delisted, selective/empty) arrive in a later phase, with the cart/Product Picker selection role.

## Scraper plugin routes — Dragon Store (implemented)

Registered under `/api/plugins/dragon-store` (the generic convention above); the scrape-now command and its per-scraper cooldown are provided by the `ScraperPlugin` base, not re-implemented by the plugin.

| Method | Path | Role | Notes |
|---|---|---|---|
| POST | `/api/plugins/dragon-store/test` | 👤 | dry-run: returns `list[Product]`, writes nothing (SCR-R11) |
| POST | `/api/plugins/dragon-store/scrape-now` | 👤 | immediate scrape for the requesting user only (writes the catalog); a run already in progress (scheduled or manual) → **409** (`scrape_in_progress`, SCHED-R4); within the cooldown → **429** with the time remaining; otherwise **202** + a background job (SCR-R15) |
| GET | `/api/plugins/dragon-store/scrape-now` | 👤 | cooldown status: `{available, available_at, retry_after_seconds, interval_seconds}` (feeds the UI countdown) |
| GET/POST/DELETE | `/api/plugins/dragon-store/watches` | 👤 | the user's watched product URLs; `POST` rejects a duplicate URL with **409** |

## Health — [deployment](../infrastructure/deployment.md)

| Method | Path | Role | Response | Notes |
|---|---|---|---|---|
| GET | `/api/health` | 🌐 | `200 {status, db, version, worker_heartbeat_age_s}` / `503` | app alive + DB reachable; `version` is the baked product version; `worker_heartbeat_age_s` is `null` until the worker persists its heartbeat (phase 4) |
