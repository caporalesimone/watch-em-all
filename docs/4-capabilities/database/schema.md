# Database — Logical schema

> **Layer 4 — Capability** · Audience: developer.
>
> English translation of the Italian reference [`docs-ita/4-capabilities/database/schema.md`](../../../docs-ita/4-capabilities/database/schema.md), limited to what is implemented (DOC-12). Phase 1 ships the `users` table; phase 3 adds the per-user catalog (`products`), its append-only price history (`price_history`) and the manual-scrape cooldown anchor (`scrape_cooldown`); phase 4 adds the scheduling, worker-run, log and scrape-cache tables; phase 5 adds the `carts` and `cart_members` tables; phase 6 adds the alert tables (`cart_alert_types`, `alert_snapshot`, `alert_log`). The notifier/delivery, summary and admin-message tables arrive in later phases.

Engine **PostgreSQL 16**, accessed via SQLAlchemy, I/O validated with Pydantic v2. The schema is created idempotently at startup by web and worker (`create_all`).

## Auth

| Table | Columns | Notes |
|---|---|---|
| `users` | id, username **UNIQUE**, first_name, last_name, password_hash, role (`admin`\|`user`), is_active, deletion_marked_at (timestamptz, null), deletion_due_at (timestamptz, null), last_login_at (timestamptz, null), locale, must_change_password, token_version, refresh_jti, created_at | **first_name + last_name** are required for admin-created accounts (USR-R15); the bootstrap admin starts with `first_name="Admin"` and an empty surname. `refresh_jti` = last issued refresh (rotation); `token_version` = global invalidation. The deletion/last-login fields are used from later phases (USR). |

## Catalog & history

| Table | Columns | Notes |
|---|---|---|
| `products` | id, user_id FK **CASCADE**, plugin_id, external_id, url, name, image_url, brand_text, brand_link, tags (JSON), category (JSON), extra_json (JSON), currency, price_current, price_original, discount_pct, is_available, removed, first_seen_at, last_seen_at | **UNIQUE (user_id, plugin_id, external_id)** = product identity; per-user catalog. `brand_text`/`brand_link` (PROD-R6, optional link), `tags` (JSON array of strings, PROD-R5) and `category` (JSON array of `{text, link}`, breadcrumb, PROD-R7) are scraper data, persisted without interpretation |
| `price_history` | id, product_id FK **CASCADE**, user_id, price_current, price_original, discount_pct, is_available, recorded_at | Append-only; one entry **only** on a price **or** availability change; INDEX (product_id, recorded_at); **no retention** |

## Manual scrape

| Table | Columns | Notes |
|---|---|---|
| `scrape_cooldown` | id, plugin_id, user_id FK **CASCADE**, last_scraped_at — **UNIQUE (plugin_id, user_id)** | the "last scrape" anchor per *(scraper, user)* for the manual **scrape-now** cooldown (SCR-R15): written at the **start** of **every** scrape (manual now; scheduled from phase 4), but **read** — and therefore binding — **only** by the manual scrape-now; upserted, one row per pair (not a run log) |

## Carts (phase 5)

| Table | Columns | Notes |
|---|---|---|
| `carts` | id, user_id FK **CASCADE**, name, mode (`cross`\|`scraper_specific`), scraper_id (String, null), threshold_amount (Numeric(12,2), null), created_at | per-user (DB-R1). `mode` fixed at creation (CART-R2); `scraper_id` = the scraper's `plugin_id` for `scraper_specific`, **NULL** for `cross` (CART-R4/R5). `threshold_amount` = the savings threshold, an **absolute €** value (`> 0`) or **NULL** = none (CART-R9); the percentage is only a UI input aid, never stored |
| `cart_members` | id, cart_id FK **CASCADE**, product_id FK **CASCADE** — **UNIQUE (cart_id, product_id)** | a product's membership in a cart (CART-R1). Both FKs cascade: deleting the cart drops its members; deleting the catalog product removes it from every cart (CAT-R8). The UNIQUE constraint makes adds idempotent. No membership state is stored — active/excluded is derived from the product's `is_available`/`removed` by the Cart Engine |

## Alerts (phase 6)

| Table | Columns | Notes |
|---|---|---|
| `cart_alert_types` | id, cart_id FK **CASCADE**, alert_type — **UNIQUE (cart_id, alert_type)** | the alert types enabled on a cart (6.B1). **Presence of a row = enabled** (no `enabled` column); `alert_type` is an [`AlertType`](../contracts/alert-event.md) value. Enabling the first type **seeds** the baseline; clearing them all **deletes** it |
| `alert_snapshot` | user_id FK **CASCADE**, cart_id FK **CASCADE**, snapshot_json (JSON), taken_at — **PK (user_id, cart_id)** | the per-(user, cart) **baseline** the diff compares against: for each non-delisted member `{on_sale, available, price_current}`, plus cart-level `all_on_sale` / `threshold_reached`. Seeded on the first alert type enabled, **advanced every run**, deleted when all types are disabled (6.B2/6.B3) |
| `alert_log` | id, user_id FK **CASCADE**, kind (`alert_digest`\|…), admin_message_id (Integer, null — its FK/table land in phase 10), payload_json (JSON), created_at, read_at (null = unread) | one in-app notification, **written always** (6.B6); INDEX (user_id, created_at). `payload_json` is the self-sufficient digest (Decimal as string, datetime ISO-8601, DB-R3). `read_at` null = unread (the sidebar badge). Phase 6 writes only `alert_digest`; per-channel delivery outcomes are recorded in `alert_delivery` (phase 7) |

## Notifiers (phase 7)

| Table | Columns | Notes |
|---|---|---|
| `alert_delivery` | id, alert_log_id FK **CASCADE**, plugin_id (empty for the no-notifier marker), status, error (null), created_at, updated_at — INDEX (alert_log_id), INDEX (status) | one **per-channel delivery outcome** for a notification. `status` ∈ `pending`\|`delivered`\|`failed`\|`skipped`\|`skipped_no_notifier`. The **in-app** channel is local → written `delivered` (or `skipped` if admin-disabled) inline; network channels start `pending` and the worker's periodic **drain** step sends them and sets `delivered`/`failed` (best-effort, no re-drain). `skipped_no_notifier` (single row, empty `plugin_id`) when the user has no active channel |
| `notifier_admin_config` | plugin_id PK, config_json (JSON), enabled (bool, default true), updated_at | per-notifier **admin** config + the **kill-switch** (`enabled`, PCFG-R8): off = channel unavailable to everyone, personal configs preserved. `config_json` holds the declared admin fields (e.g. SMTP host/credentials, secrets included). In-app has a row too (only `enabled` matters) |
| `notifier_user_config` | user_id FK **CASCADE**, plugin_id, config_json (JSON), enabled (bool, default false), updated_at — **PK (user_id, plugin_id)** | per-user personal config + the user's own on/off (disabling keeps the config, PROF-R10). The **in-app** channel is exempt (no row): the user cannot disable it |

## Scheduling & monitoring (phase 4)

| Table | Columns | Notes |
|---|---|---|
| `scraper_schedule` | scraper_id PK, times (JSON, canonical `"HH:MM:SS"`), enabled, last_slot (timestamptz, null = never) | 1..N slots/day; input `HH:MM`/`HH:MM:SS` → stored canonical `HH:MM:SS` (4.F1); `last_slot` = last executed slot |
| `scraper_admin_config` | plugin_id PK, config_json, updated_at | per-scraper admin config (PCFG, 4.B10): `config_json` holds the **plugin-declared fields** (site rules, phase 7+) **and** the **core reserved keys** (`politeness_delay_ms`, `http_timeout_s`, `cache_ttl_min`, `scrape_now_min_interval_s`) read by the core (HTTP client, cache, scrape-now cooldown), not the plugin (CTX); defaults mirror the superseded constants, overrides merged, unknown keys ignored. **No `enabled`** — suspension lives in `scraper_schedule` |
| `feature_flags` | key PK, value (JSON) | **dev feature flags** (4.B1a): runtime overrides of dev-only knobs, shared between web and worker (separate processes); the web **clears them at startup** → non-persistent. Set by the admin via Swagger (`PATCH /api/admin/feature-flags`). First flag: `worker_tick.seconds` |
| `system_settings` | key PK, value_json, updated_at | runtime settings ([SystemSettings](../contracts/scheduling-models.md)); defaults seeded at first start |
| `scrape_run` | run_id, scraper_id, trigger, slot, started_at, finished_at, status, users_processed, products_found, products_new, price_changes, products_removed, products_excluded, http_requests, cache_hits, error_message | one row per run; INDEX (scraper_id, started_at); retention |
| `scrape_user_log` | run_id FK **CASCADE**, user_id, started_at, finished_at, products_found, products_new, price_changes, http_requests, cache_hits, status, error_message | per-user detail; http_requests/cache_hits attributed to the user in flight (single-threaded run); retention |
| `scrape_cache` | id, plugin_id, cache_key, response_body, response_meta_json (status, content-type), fetched_at, expires_at | scrape response cache ([plugin-context](../core/plugin-context.md), CTX-R9): cache_key = hash of the normalised request; **UNIQUE (plugin_id, cache_key)**; INDEX (expires_at); expired rows dropped at run start, manual clear from the scraper's admin page |
| `system_log` | id (incremental PK, polling cursor), created_at, level, source (`worker`\|`scraper`\|`web`\|`notifier`\|`alert`\|`summary`), message, context_json | INDEX (id); retention; never users' operational content |

## Cross-cutting rules (implemented subset)

- **DB-R1** — Every operational table carries `user_id`; every application query filters by the token's user (multi-tenancy). `products`/`price_history` are scoped this way; `products` cascades to `price_history` on delete.
- **DB-R4** — **Migrations**: additive schema with `CREATE ... IF NOT EXISTS`; breaking changes need documented manual SQL — **never** drop & recreate the whole schema. In phase-1 development, adding columns to `users` is applied by recreating the dev database (`docker compose down -v`); a migration tool (Alembic) is a future improvement.
- **DB-R5** — Backup/export/restore via the versioned `ops/` scripts baked into the `ops` image (see [backup-and-restore](../../infrastructure/deployment.md)).
