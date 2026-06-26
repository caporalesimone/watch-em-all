# Database — Logical schema

> **Layer 4 — Capability** · Audience: developer.
>
> English translation of the Italian reference [`docs-ita/4-capabilities/database/schema.md`](../../../docs-ita/4-capabilities/database/schema.md), limited to what is implemented (DOC-12). Phase 1 ships the `users` table; phase 3 adds the per-user catalog (`products`), its append-only price history (`price_history`) and the manual-scrape cooldown anchor (`scrape_cooldown`); phase 4 adds the scheduling, worker-run, log and scrape-cache tables; carts and alerts arrive in later phases.

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
| `system_log` | id (incremental PK, polling cursor), created_at, level, source (`worker`\|`scraper`\|`notifier`\|`alert`\|`summary`), message, context_json | INDEX (id); retention; never users' operational content |

## Cross-cutting rules (implemented subset)

- **DB-R1** — Every operational table carries `user_id`; every application query filters by the token's user (multi-tenancy). `products`/`price_history` are scoped this way; `products` cascades to `price_history` on delete.
- **DB-R4** — **Migrations**: additive schema with `CREATE ... IF NOT EXISTS`; breaking changes need documented manual SQL — **never** drop & recreate the whole schema. In phase-1 development, adding columns to `users` is applied by recreating the dev database (`docker compose down -v`); a migration tool (Alembic) is a future improvement.
- **DB-R5** — Backup/export/restore via the versioned `ops/` scripts baked into the `ops` image (see [backup-and-restore](../../infrastructure/deployment.md)).
