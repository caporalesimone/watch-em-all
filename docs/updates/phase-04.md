# Phase 4 — Worker & scheduling

> Feature-level recap. Phase 4 is **in progress**. The headline — automatic scheduled
> scraping with an observable worker — is still ahead (4.B2+). What's landed so far
> (`0.4.0`) is the **developer / admin tooling** the rest of the phase builds on: a
> schema-drift safety net, a friendlier dev database browser, admin plugin versions,
> and a tidy-up of the environment variables.

## What's implemented (so far, 0.4.0)

### 1) Dev database browser: Adminer → pgweb

- The development stack now ships **pgweb** instead of Adminer. It comes up with the
  normal `docker compose -f compose-dev.yml up` (no profile to remember) and opens
  **straight on the `watchemall` database** — no connection form, no login (the
  connection is built from your `POSTGRES_*`).
- The **release** deploy kit no longer carries any DB browser: it stays strictly
  production-shaped. To inspect the DB on a server, use `docker compose exec db psql …`
  or the `ops` container.

### 2) Schema-drift safety net + admin errors feed

- On startup the app compares the database with the code's data model. If a table or
  column the code expects is **missing** from the DB — the situation a model change
  creates on an existing dev database, since there are no migrations yet — it logs a
  clear warning and (with the alert on) surfaces it to the **admin**.
- The admin sees a **red banner** (bottom-right, detached from the edges) with a
  **Copy Message** button that copies the problem as JSON and a **✕** to dismiss it.
  It's **admin-only**: a normal or anonymous user never sees it, and the data is served
  by an admin-only endpoint (`GET /api/admin/errors`), never the public health probe.
- It's a generic **admin errors feed**: schema drift is the first entry; future admin
  problems (worker down, a plugin that failed to load, …) will appear the same way,
  stacked one card per problem.

### 3) Admin can see plugin versions

- A new **Admin → Plugins** page lists each loaded plugin with its **type and version**
  (e.g. Dragon Store `0.2.0`) — the first slice of admin plugin visibility.

### 4) Environment variables standardized

- Every Watch 'Em All variable is now prefixed **`WEA_`** (e.g. `SECRET_KEY` →
  `WEA_SECRET_KEY`, `ADMIN_INITIAL_USERNAME`/`ADMIN_INITIAL_PASSWORD` →
  `WEA_ADMIN_INITIAL_*`). External names the images expect (`POSTGRES_*`, `TZ`) are
  unchanged. A new [`docs/env-variables.md`](../env-variables.md) lists them all.

_Under the hood:_ the drift check (`src/core/schema_drift.py`) runs after the schema is
ensured and iterates the core `Base.metadata` plus each plugin's declared
`table_metadata` — a new contract (DB-R7) the registry enforces at load, so a plugin
that owns tables but doesn't declare them is rejected. pgweb is dev-only and always-on
(no Compose profile); the gate that keeps debug tools out of production moved from a
profile to file separation (`compose-dev.yml` vs `compose.yml`). The product version is
still baked from the git tag; `WEA_VERSION` only selects which image the release compose
pulls.

## Good to know

- The **worker is now the real dispatcher skeleton** (it boots like the web and writes
  a per-minute heartbeat), but the automatic **scheduling** — per-scraper slots, the
  serial runner, run/log records — arrives in the next MVPs (4.B2+). `/api/health` still
  shows `worker_heartbeat_age_s: null` (the worker's heartbeat is a file for the
  container healthcheck; surfacing it on health comes later).
- The schema-drift alert ships **on in dev**: `WEA_SCHEMA_DRIFT_ALERT=true` in
  `.env`/`.env.example`; if the variable is unset the app defaults to **off**. It never
  reaches a non-admin.
- To see the drift banner: as **admin**, break the schema on purpose, then restart web
  (see Useful Commands). Reset the dev DB to clear it.

## Useful Commands

```bash
docker compose -f compose-dev.yml up -d --build         # db + web + worker + pgweb (DB browser on :8081)
docker compose -f compose-dev.yml down -v               # reset the DB (admin recreated from .env)

# See the admin schema-drift banner: as admin, create drift then restart web
docker compose -f compose-dev.yml exec db psql -U admin -d watchemall -c "ALTER TABLE products DROP COLUMN tags;"
docker compose -f compose-dev.yml restart web
```

**pgweb** (DB browser) — http://localhost:8081, opens straight on the `watchemall`
database (no connection form, no login).
