# Database — Logical schema

> **Layer 4 — Capability** · Audience: developer.
>
> English translation of the Italian reference [`docs-ita/4-capabilities/database/schema.md`](../../../docs-ita/4-capabilities/database/schema.md), limited to what is implemented (DOC-12). Phase 1 ships the `users` table only; the catalog, carts, alerts and scheduling tables arrive in later phases.

Engine **PostgreSQL 16**, accessed via SQLAlchemy, I/O validated with Pydantic v2. The schema is created idempotently at startup by web and worker (`create_all`).

## Auth

| Table | Columns | Notes |
|---|---|---|
| `users` | id, username **UNIQUE**, first_name, last_name, password_hash, role (`admin`\|`user`), is_active, deletion_marked_at (timestamptz, null), deletion_due_at (timestamptz, null), last_login_at (timestamptz, null), locale, must_change_password, token_version, refresh_jti, created_at | **first_name + last_name** are required for admin-created accounts (USR-R15); the bootstrap admin starts with `first_name="Admin"` and an empty surname. `refresh_jti` = last issued refresh (rotation); `token_version` = global invalidation. The deletion/last-login fields are used from later phases (USR). |

## Cross-cutting rules (implemented subset)

- **DB-R1** — Every operational table carries `user_id`; every application query filters by the token's user (multi-tenancy). *(No operational tables yet in phase 1.)*
- **DB-R4** — **Migrations**: additive schema with `CREATE ... IF NOT EXISTS`; breaking changes need documented manual SQL — **never** drop & recreate the whole schema. In phase-1 development, adding columns to `users` is applied by recreating the dev database (`docker compose down -v`); a migration tool (Alembic) is a future improvement.
- **DB-R5** — Backup/export/restore via the versioned `ops/` scripts baked into the `ops` image (see [backup-and-restore](../../infrastructure/deployment.md)).
