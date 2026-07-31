# API — Endpoint catalogue

> The single, canonical reference of the core HTTP endpoints. Conventions and Swagger: [README.md](README.md).
>
> English translation of the Italian reference [`docs-ita/api/endpoints.md`](../../docs-ita/api/endpoints.md), limited to what is implemented (DOC-12). Phase 1 ships Auth, Me and Health; phase 3 adds admin user management, plugin discovery, the read-only **catalog** and the scraper plugin's own routes; phase 4 adds the scraper scheduling/worker admin, the system log and the runtime settings/feature-flags; phase 5 adds **carts** (CRUD, membership and the computed state); phase 6 adds the per-cart **alert types** and the in-app **alert history**. Cart/product **history** and **notifier** delivery arrive in later phases.

Role legend: 🌐 public · 👤 user · ⚡ super-user (and admin) · 🛡 admin

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
| POST | `/api/admin/users` | 🛡 | `{username, first_name, last_name, role, temp_password}` | creates an account with a forced first-login password change; duplicate username → 409 (USR-R1/R2/R15). `role` ∈ {`user`, `super_user`, `admin`} — chosen here and not changed afterwards (promoting an existing account is a later phase) |
| GET | `/api/admin/users` | 🛡 | — | lists all accounts (username, name, role, status, last login) |

## Admin — system

| Method | Path | Role | Response | Notes |
|---|---|---|---|---|
| GET | `/api/admin/errors` | 🛡 | `[{source, type, title, description}]` | **admin-only** feed of errors/warnings (admin diagnostics), kept off the public `/api/health` probe. First source: schema drift (4.B0), behind `WEA_SCHEMA_DRIFT_ALERT` |
| GET | `/api/admin/logs` | 🛡 | `[{id, created_at, level, source, message, context}]` | **admin-only** system log **live tail** (4.B7/4.F3). Cursor by `id`: no `since` → latest `limit`; `since=<id>` → rows with `id > since` (ascending). Filters `level` (info/warning/error), `sources` (repeatable, multi), `q` (case-insensitive message search); `limit` 1–1000 (default 200) |
| GET | `/api/admin/logs/page` | 🛡 | `{items, total, counts:{info,warning,error}, sources}` | **admin-only** system log **paged history** (4.F4): `page`+`size` (newest-first window) + `total` + per-level `counts` (over the source/search filters) + distinct `sources` (filter chips). Same `level`/`sources`/`q` filters |
| GET | `/api/admin/feature-flags` | 🛡 | `{key: {…}}` | dev feature flags, effective values (defaults + overrides). Admin-only (4.B1a) |
| PATCH | `/api/admin/feature-flags` | 🛡 | `{key: {…}}` | set one or more flags (known keys only); returns the effective map. Non-persistent — reset at web startup |
| GET | `/api/admin/settings` | 🛡 | `{scraper_run_timeout_min, catchup_warning_min, log_retention_days, user_deletion_retention_days}` | system settings, effective (defaults + overrides). Admin only (4.F7) |
| PATCH | `/api/admin/settings` | 🛡 | same shape (partial) | set one or more known settings (merged, ranges validated); **422** on unknown key / out-of-range. DB-first, no restart |

Known flags (params shown with their defaults): `worker_tick` `{seconds: 60}` (worker dispatcher tick). _(The manual scrape-now cooldown is no longer a dev flag — it is the per-scraper reserved key `scrape_now_min_interval_s`, 4.B10.)_

## Admin — scrapers — [scraper-scheduling-and-limits](../3-features/admin/scraper-scheduling-and-limits.md)

| Method | Path | Role | Response | Notes |
|---|---|---|---|---|
| GET | `/api/admin/scrapers` | 🛡 | `[{scraper_id, display_name, times, enabled, last_slot, cache_entries}]` | schedulable scrapers (those that implement scraping) + their schedule and current scrape-cache size (4.B2) |
| PUT | `/api/admin/scrapers/{scraper_id}` | 🛡 | `{times, enabled}` → `{scraper_id, times, enabled, last_slot}` | set the slots (input `"HH:MM"` or `"HH:MM:SS"`, **returned canonical `"HH:MM:SS"`** (4.F1), de-duplicated/sorted; **422** on a bad time) and the enabled flag; unknown scraper → **404**. Edited from the **Scrapers → Schedule** page |
| DELETE | `/api/admin/scrapers/{scraper_id}/cache` | 🛡 | `{deleted}` | clear the scraper's scrape cache (CTX-R9, 4.B9); returns how many entries were removed; unknown scraper → **404** |
| GET | `/api/admin/scrapers/{scraper_id}/config` | 🛡 | `{politeness_delay_ms, http_timeout_s, cache_ttl_min, scrape_now_min_interval_s}` | the scraper's **core reserved config** — effective values (defaults + overrides, 4.B10); unknown scraper → **404** |
| PATCH | `/api/admin/scrapers/{scraper_id}/config` | 🛡 | same shape | set one or more reserved keys (merged over the current values); **422** on an unknown key or out-of-range value, **404** unknown scraper |

## Plugin discovery — [plugin-registry](../4-capabilities/core/plugin-registry.md)

| Method | Path | Role | Response | Notes |
|---|---|---|---|---|
| GET | `/api/plugins` | 👤🛡 | `[{name, type, route_base, icon, display_name, version}]` | only enabled + loaded plugins; no internal paths. `route_base`/`icon` are `null` for a plugin without a frontend (notifiers); `version` is the plugin's own manifest version (4.B0a) |
| GET | `/api/plugin-assets/{name}/icon` | 🌐 | image | the plugin's manifest `icon`, served as a static asset (path-traversal guarded); 404 if absent. Public like the SPA bundle — the browser loads it as an `<img>`, which cannot carry the bearer token |

Plugin-specific routes are registered by each plugin under `/api{route_base}` (e.g. `/api/plugins/my-store/...`), **behind authentication** (the registry applies a user dependency to every plugin router), and documented in OpenAPI under the `Plugin: <name>` tag.

## Catalog — [catalog-update-service](../4-capabilities/core/catalog-update-service.md)

| Method | Path | Role | Query | Notes |
|---|---|---|---|---|
| GET | `/api/catalog` | 👤 | `?page=&page_size=&sort=&order=&q=&available=&removed=` | the current user's catalog as the Product Picker table: paginated server-side, returns `{items, total, page, page_size}`. `sort` ∈ {`name`, `plugin_id`, `price_current`, `price_original`, `is_available`, `last_seen_at`} (default `last_seen_at`); `order` `asc`\|`desc`; `q` = case-insensitive name search; `available`/`removed` = optional boolean filters. Each item carries `sources: [{kind, label}]` — which of the user's inputs still deliver it (C14, PROD-R9), so the deletion confirmation can name what will bring it back; empty means nothing will |

| GET | `/api/catalog/delisted` | 👤 | — | `{total, in_carts}` — what "remove the delisted" is about to do (C7): every delisted row of the user's catalog, and how many of them are in at least one cart. Counted server-side over the whole catalog, never the visible page |
| DELETE | `/api/catalog/delisted` | 👤 | — | remove every delisted product of the current user → `{removed}`. The routine tidy-up |
| DELETE | `/api/catalog/{product_id}` | 👤 | — | remove one product → `{removed: 1}`. Someone else's product answers **404**, never 403: a 403 would confirm the row exists |
| DELETE | `/api/catalog` | 👤 | — | empty the catalog → `{removed}`. The **watches survive**, so the next run refills what is still watched — which is why the confirmation has to say so (CAT-R6) |

The catalog is otherwise **read-only** here: it is filled only through the Catalog Update Service (a scrape). The three deletions are the user's own cleanups (9.B7/9.F4); each takes the product's **price history and cart memberships** with it (CAT-R8, an `ON DELETE CASCADE`) and reports how many rows went, so the page can say what happened instead of just refreshing.

## Price history — [price-history](../4-capabilities/core/price-history.md)

| Method | Path | Role | Query | Notes |
|---|---|---|---|---|
| GET | `/api/products/{id}/history` | 👤 | `?range=week\|month\|all` | the product's stepped price/availability series, ready for the chart: `{product_id, range, points}`, `points: [{t, price, available}]` ordered oldest→newest (`price` an exact decimal string). `available=false` marks where the line must **break** (no interpolation, HIST-R2). For `week`/`month` the value in effect at the window start is included, **clamped** to it, so the line starts at the right price. Another user's product → **404** `product_not_found` |
| GET | `/api/carts/{id}/history` | 👤 | `?range=week\|month\|all` | the cart's stepped **total** series: `{cart_id, range, points}`, `points: [{t, total}]`. The sum of the cart's **current** members, each contributing its price only while it was **available** (unavailable stretches excluded); the current composition is projected onto the past — no membership history (HIST-R4). Another user's cart → **404** |

`range` defaults to `month`. Series are served ready to plot — the SPA does not aggregate (HISTC-R4).

## Carts — [cart-engine](../4-capabilities/core/cart-engine.md)

| Method | Path | Role | Body | Notes |
|---|---|---|---|---|
| GET | `/api/carts` | 👤 | — | the user's carts as **cards** (each with its computed state: totals, adjustments, final estimate, threshold, health flag), newest first |
| POST | `/api/carts` | 👤 | `{name, mode, scraper_id?}` | create; `mode` ∈ {`cross`, `scraper_specific`} and is **immutable** afterwards (CART-R2). `scraper_specific` **requires** a loaded `scraper_id` (else **422** `scraper_id_required` / `unknown_scraper`); `cross` must **not** name one (**422** `scraper_id_not_allowed`). Returns the cart **detail** with **201** |
| GET | `/api/carts/{id}` | 👤 | — | the cart **detail**: the card fields + the member rows (each with provenance, prices, availability, `active`). Another user's cart → **404** |
| PATCH | `/api/carts/{id}` | 👤 | `{name?, threshold_amount?}` | rename and/or set the savings threshold. `threshold_amount` is an **absolute €** value (`> 0`, else **422** `threshold_must_be_positive`); `threshold_amount: null` clears it. The % is only a UI input aid (CART-R9); the mode cannot be changed |
| DELETE | `/api/carts/{id}` | 👤 | — | **204**; deletes only the cart (members cascade; catalog products untouched, CART-R3) |
| POST | `/api/carts/{id}/items` | 👤 | `{product_ids}` | add members (idempotent). Batch-validated: your catalog only (**422** `product_not_found`), no delisted (**422** `product_delisted`), single currency (**422** `currency_mismatch`), and for `scraper_specific` only that scraper's products (**422** `product_scraper_mismatch`). Returns the updated detail |
| DELETE | `/api/carts/{id}/items` | 👤 | `{product_ids}` | remove members; absent ids are a no-op. Returns the updated detail |
| PUT | `/api/carts/{id}/alert-types` | 👤 | `{alert_types: [...]}` | set the **full** set of enabled alert types on the cart (presence = enabled; 6.B1). Values validated against the `AlertType` enum (**422** `unknown_alert_type`). Enabling the first type **seeds the baseline**; an empty list **deletes** it. Returns the updated detail (whose `alert_types` reflects the set) |

The cart state (totals over the **active** members, adjustments for scraper-specific carts, the final estimate, the threshold state and the `has_delisted` health flag) is computed on demand by the [Cart Engine](../4-capabilities/core/cart-engine.md) — nothing is persisted beyond the cart definition and its members. The cart **price history** (stepped total over time) is served by `GET /api/carts/{id}/history` — see [Price history](#price-history--price-history) above.

## Alerts — [alert-engine](../4-capabilities/core/alert-engine.md)

The in-app alert history (phase 6). Alerts are **event-driven**: the engine runs after each scrape that changed the user's catalog and writes at most one aggregated digest per user (no cadence). Per-channel **delivery** and its outcomes are phase 7 (see Notifiers below). The **in-app** channel is itself a notifier (`in_app`): the list/badge/detail below are hidden when an admin has globally disabled it.

| Method | Path | Role | Body / Query | Notes |
|---|---|---|---|---|
| GET | `/api/alerts` | 👤 | `?page=&page_size=&kind=` | the user's notifications, newest first, paginated → `{items, total, page, page_size}`. Each item: `{id, kind, created_at, read, cart_count}`. Optional `kind` filter. **Empty when the admin has disabled the in-app channel** |
| GET | `/api/alerts/unread-count` | 👤 | — | `{count}` — the unread count for the sidebar badge (**0** when the in-app channel is admin-disabled) |
| GET | `/api/alerts/{id}` | 👤 | — | one notification in full: `{id, kind, created_at, read, payload, deliveries}` — `payload` is the self-sufficient digest; `deliveries` is the per-channel outcomes `[{plugin_id, status, error, updated_at}]` (7.F5), `status` ∈ `pending`\|`delivered`\|`failed`\|`skipped`\|`skipped_no_notifier`. Another user's alert → **404** |
| POST | `/api/alerts/{id}/read` | 👤 | — | **204**; mark read (idempotent — keeps the first read timestamp). Another user's alert → **404** |
| DELETE | `/api/alerts` | 👤 | `{ids: [...]}` | **204**; bulk-delete the user's own alerts (multi-select). Ids the caller doesn't own are simply not matched |

## Notifiers (user) — [profile-and-notifiers](../3-features/user/profile-and-notifiers.md)

The user's notification channels (phase 7). A channel the admin has globally disabled is **not listed**. The **in-app** channel appears but has no user config and cannot be disabled by the user (always active). Secrets are write-only: never returned, only an `is_set` flag.

| Method | Path | Role | Body | Notes |
|---|---|---|---|---|
| GET | `/api/notifiers` | 👤 | — | per channel: `{plugin_id, display_name, is_in_app, user_schema, config, is_set, available, user_config_complete, enabled, active}`. `config` holds only non-secret stored values |
| PUT | `/api/notifiers/{plugin_id}/config` | 👤 | `{config}` | save the personal config; keys filtered on the user schema (CFG-R5), an omitted secret keeps the stored value (CFG-R3). In-app → **422** `in_app_no_config`. Unknown → **404** |
| PATCH | `/api/notifiers/{plugin_id}` | 👤 | `{enabled}` | activate/deactivate for the user (config preserved). In-app → **422** `in_app_always_active` |
| POST | `/api/notifiers/{plugin_id}/test` | 👤 | — | send a test to the user's own target (synchronous, no persistence) → `{ok, error}` |

## Admin — notifiers (system config) — [notifier-plugin](../3-features/plugins/notifier-plugin.md)

| Method | Path | Role | Body | Notes |
|---|---|---|---|---|
| GET | `/api/admin/notifiers` | 🛡 | — | per channel: `{plugin_id, display_name, is_in_app, admin_schema, user_schema, config, is_set, enabled, admin_config_complete}` (`user_schema` feeds the channel-test target) |
| PUT | `/api/admin/notifiers/{plugin_id}/config` | 🛡 | `{config}` | set the system config; keys filtered on the admin schema, secrets write-only. In-app → **422** `in_app_no_config` |
| PATCH | `/api/admin/notifiers/{plugin_id}` | 🛡 | `{enabled}` | global **kill-switch** (PCFG-R8): off = unavailable to everyone, personal configs preserved. Applies to in-app too |
| POST | `/api/admin/notifiers/{plugin_id}/test` | 🛡 | `{config}` | probe the channel with the system config + an admin-supplied target (filtered on the user schema; not persisted) → `{ok, error}` |

## Scraper plugin routes — Dragon Store (implemented)

Registered under `/api/plugins/dragon-store` (the generic convention above); the scrape-now command and its per-scraper cooldown are provided by the `ScraperPlugin` base, not re-implemented by the plugin.

| Method | Path | Role | Notes |
|---|---|---|---|
| POST | `/api/plugins/dragon-store/scrape-now` | ⚡ | immediate scrape for the requesting user only (writes the catalog); **super-user or admin** (9.B8) — a plain user gets **403**; a run already in progress (scheduled or manual) → **409** (`scrape_in_progress`, SCHED-R4); within the cooldown → **429** with the time remaining; otherwise **202** + a background job (SCR-R15) |
| GET | `/api/plugins/dragon-store/scrape-now` | ⚡ | cooldown status: `{available, available_at, retry_after_seconds, interval_seconds}` (feeds the UI countdown). Same restriction as the POST: the status of a command you cannot issue is not yours either |
| GET | `/api/plugins/dragon-store/classify` | 👤 | `?url=` → `{kind}`: `"product"`, `"category"` or `null`. Decided from the URL alone, no request to the store; the add form asks while the URL is being pasted, so the dented toggle appears only for a category |
| GET/POST/DELETE | `/api/plugins/dragon-store/watches` | 👤 | the user's watched products **and categories**; `POST {url, include_ammaccati?}` commits the row and queues it, answering **201** in milliseconds — the row *is* the job, resolved outside the request (9.X6b). A duplicate URL → **409** `duplicate_watch` (a UNIQUE, not a check); another add still in flight → **409** `add_in_progress`; an unrecognised URL → **422** `invalid_url`. `include_ammaccati` is dropped on a product URL (DRG-R7). Each row carries what its last scan yielded: `products_included`, `products_excluded`, `last_scanned_at` |
| PATCH | `/api/plugins/dragon-store/watches/{id}` | 👤 | `{include_ammaccati}` — the dented filter on an existing **category**, applied from the next scan. A product watch → **422** `not_a_category`; a watch being resolved → **409** `watch_busy` (the walk reads that column between pages); someone else's → **404** |

## Health — [deployment](../infrastructure/deployment.md)

| Method | Path | Role | Response | Notes |
|---|---|---|---|---|
| GET | `/api/health` | 🌐 | `200 {status, db, version, server_time, worker_heartbeat_age_s}` / `503` | app alive + DB reachable; `version` is the baked product version; `server_time` is ISO8601 with the installation-TZ offset (the UI clock source, 4.F1); `worker_heartbeat_age_s` is `null` until the worker persists its heartbeat (phase 4) |
