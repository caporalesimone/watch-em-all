# Database — Logical schema

> **Layer 4 — Capability** · Audience: developer.
>
> English translation of the Italian reference [`docs-ita/4-capabilities/database/schema.md`](../../../docs-ita/4-capabilities/database/schema.md), limited to what is implemented (DOC-12). Phase 1 ships the `users` table; phase 3 adds the per-user catalog (`products`) and its append-only price history (`price_history`); carts, alerts and scheduling tables arrive in later phases.

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

## Cross-cutting rules (implemented subset)

- **DB-R1** — Every operational table carries `user_id`; every application query filters by the token's user (multi-tenancy). `products`/`price_history` are scoped this way; `products` cascades to `price_history` on delete.
- **DB-R4** — **Migrations**: additive schema with `CREATE ... IF NOT EXISTS`; breaking changes need documented manual SQL — **never** drop & recreate the whole schema. In phase-1 development, adding columns to `users` is applied by recreating the dev database (`docker compose down -v`); a migration tool (Alembic) is a future improvement.
- **DB-R5** — Backup/export/restore via the versioned `ops/` scripts baked into the `ops` image (see [backup-and-restore](../../infrastructure/deployment.md)).
