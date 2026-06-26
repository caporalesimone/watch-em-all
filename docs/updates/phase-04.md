# Phase 4 — Worker & scheduling

> Feature-level recap. Phase 4 is **in progress**. The headline — **automatic scheduled
> scraping with an observable worker** — is now in (`0.4.0`), together with the dev/admin
> tooling around it: a transparent scrape cache, a system log with retention, dev feature
> flags and the admin pages, on top of the earlier groundwork (a friendlier dev database
> browser, a schema-drift safety net, admin plugin versions, tidier environment variables).
> The i18n consistency tool (dev/CI) is the last remaining MVP before the phase closes.

## What's implemented (so far, 0.4.0)

### 1) Automatic scheduled scraping (the worker)

- An admin sets per-scraper **daily times** (`PUT /api/admin/scrapers/{id}`) and the worker
  runs each scraper automatically at those times — **one scraper at a time** — so your
  catalog refreshes on its own, no need to hit *Scrape now*.
- After downtime the worker **catches up** only the *most recent* missed slot (never a
  replay of every slot it was down for).
- A manual *Scrape now* and a scheduled run share the **same per-scraper lock**: a manual
  run started while one is in progress gets a clear `409`, and a scheduled slot is skipped
  if a manual run holds the lock.
- Every run is recorded (`scrape_run` + a per-user `scrape_user_log`) with counters —
  products found / new / price-changes / removed, HTTP requests, **cache hits** — and a
  status (`ok` / `partial` / `error` / `timeout`); a run that overruns the configured
  timeout is stopped between users and marked.
- Schedules are set from the **Scrapers → Schedule** page: per-scraper `HH:MM:SS` time
  chips (add/remove with confirmation, an Active/suspend toggle, and a UI rule that two runs
  must be ≥ 1 minute apart), plus a **24-hour timeline** with clickable plugin-icon markers
  and a live "now" marker read once from `/api/health` then ticked locally. Or via the API.

### 2) Scrape cache — fewer visits to the shop

- The scraper's HTTP client now serves repeated `GET`s from a per-scraper **cache** within
  a **half-life** (default 60 min): two users watching the same page in one run — or runs
  close together — cost a **single visit** to the site, counted as `cache_hits`.
- It's transparent to the plugin, only caches successful reads (never errors), and is
  bypassed when the half-life is set to 0. Expired entries are dropped at the start of each
  run, and an admin can **clear** a scraper's cache on demand
  (`DELETE /api/admin/scrapers/{id}/cache`).

### 3) A system log the admin can read

- Worker and scraper events (runs, skips, errors) are persisted to a **system log**,
  readable by the admin via `GET /api/admin/logs` — a cursor: the latest entries first,
  then only newer rows, filterable by level and source. It never carries users' product
  data, only ids and metrics.
- The worker prunes the log **and** old run records past `log_retention_days` (default 90)
  once a day; the **price history is never pruned** — it is the system's value.
- A **System logs** admin page (`/admin/logs`) reads it: a **Live** tail (cursor, auto-refresh)
  or paged **history** (page numbers + total + per-level counts), with level tabs, multi-source
  chips, message search, and a `{ }` viewer for a row's context JSON.

### 4) System settings + dev feature flags

- An **Admin → Settings** page edits the runtime `system_settings` (run timeout, log
  retention, catch-up threshold, user-deletion grace) **without a restart** (`GET`/`PATCH
  /api/admin/settings`, known keys with validated ranges); the worker re-reads them on each
  run/purge.
- **Feature flags** live as a child page under Settings: a dev-only facility to tweak a
  runtime knob (the **worker tick** interval), shared with the worker through the database
  and **reset when the web restarts** (non-persistent). The page renders itself from the API
  — each flag's input is inferred from its value's type — so a new flag shows up with no
  frontend change.

### 5) Admin sees plugins by kind — Scrapers & Notifiers

- The admin has a **Scrapers** area and a **Notifiers** area, each listing the loaded
  plugins of that kind with their **icon and version** (e.g. Dragon Store `0.2.0`).
  **Scrapers** also shows the schedule and links to each scraper's config page; **Notifiers**
  is informational for now (notifier admin config arrives in phase 7+). This replaces the
  earlier single *Plugins* list.

### 6) Dev database browser: Adminer → pgweb

- The development stack ships **pgweb** instead of Adminer. It comes up with the normal
  `docker compose -f compose-dev.yml up` (no profile to remember) and opens **straight on
  the `watchemall` database** — no connection form, no login.
- The **release** deploy kit no longer carries any DB browser: it stays strictly
  production-shaped. To inspect the DB on a server, use `docker compose exec db psql …`
  or the `ops` container.

### 7) Schema-drift safety net + admin errors feed

- On startup the app compares the database with the code's data model. If a table or
  column the code expects is **missing** — the situation a model change creates on an
  existing dev database, since there are no migrations yet — it logs a clear warning and
  (with the alert on) surfaces it to the **admin**.
- The admin sees a **red banner** with a **Copy Message** button and a **✕** to dismiss it.
  It's **admin-only**: served by `GET /api/admin/errors`, never the public health probe.
  It's a generic feed — future admin problems will appear the same way.

### 8) Environment variables standardized

- Every Watch 'Em All variable is now prefixed **`WEA_`** (e.g. `SECRET_KEY` →
  `WEA_SECRET_KEY`). External names the images expect (`POSTGRES_*`, `TZ`) are unchanged.
  A [`docs/env-variables.md`](../env-variables.md) lists them all.

### 9) Per-scraper operational settings (admin)

- An **Admin → Scrapers** area lists the schedulable scrapers (version + schedule summary)
  and opens, per scraper, a config page for the **operational parameters** the core applies
  on every run and manual scrape: **politeness delay**, **HTTP timeout**, **cache half-life**
  and the **manual scrape-now cooldown** (`GET`/`PATCH /api/admin/scrapers/{id}/config`). The
  **Clear cache** button lives here too. Changes take effect on the next run — no restart.

_Under the hood:_ the `worker` container runs the real dispatcher (`src/worker`): it boots
like the web (engine, schema, plugins) and ticks at an interval read from the
`worker_tick` feature flag (base `WEA_TICK_SECONDS`), re-read each second so a change takes
effect within ~1 s. Scheduling is a `scraper_schedule` table + admin API, a TZ-aware
due-slot/catch-up calculation, a **serial runner** (one scraper at a time, a per-scraper
advisory lock shared with scrape-now, a run timeout from `system_settings`), and
`scrape_run`/`scrape_user_log` records. The feature flags live in a `feature_flags` table
shared between web and worker and cleared at web startup. The per-scraper reserved settings
live in `scraper_admin_config`, read by `build_context` for every run and scrape-now
(superseding the former hard-coded constants and the `scrape_now_cooldown` dev flag). The system log is fed by a
logging handler attached to the `wea` logger in both processes — only `wea.worker.*` and
`wea.plugin.*` records are persisted (the web's own logs stay on stdout); retention runs
from the worker via `src/core/maintenance.py`. The scrape cache sits behind a small,
**swappable** interface (`src/core/scrape_cache.py`, today Postgres-backed) used by the
context's HTTP client, so a future Redis backend would be a localized change leaving the
client and runner untouched. The drift check (`src/core/schema_drift.py`) iterates the
core `Base.metadata` plus each plugin's declared `table_metadata` (DB-R7, enforced at
load); the product version is still baked from the git tag.

## Good to know

- **Scheduled scraping works today**, configured from the **Scrapers → Schedule** page (or the
  API `/api/admin/scrapers`), with a 24-hour timeline. A single daily time means one run per
  day — the worker is a *daily-times* scheduler, not an "every N minutes" interval.
- The **system log is API-only** for now; the near-real-time **log page** (filters,
  autoscroll) is the next frontend MVP and consumes the same cursor endpoint.
- The cache half-life and the manual scrape-now cooldown are now **per-scraper admin
  settings** (Admin → Scrapers), editable without a restart; their defaults match the
  former built-in constants.
- Feature flags are **dev-only and non-persistent** — they reset to defaults on web restart.
- The schema-drift alert ships **on in dev** (`WEA_SCHEMA_DRIFT_ALERT=true`); it never
  reaches a non-admin.

## Useful Commands

```bash
docker compose -f compose-dev.yml up -d --build         # db + web + worker + pgweb (DB browser on :8081)
docker compose -f compose-dev.yml down -v               # reset the DB (admin recreated from .env)

# Schedule a scraper (admin token required); the worker runs it at those daily times
#   PUT /api/admin/scrapers/dragon_store  {"times": ["09:00","21:00"], "enabled": true}
# Read the system log (admin):  GET /api/admin/logs?level=error&limit=50
# Clear a scraper's cache (admin):  DELETE /api/admin/scrapers/dragon_store/cache

# See the admin schema-drift banner: as admin, create drift then restart web
docker compose -f compose-dev.yml exec db psql -U admin -d watchemall -c "ALTER TABLE products DROP COLUMN tags;"
docker compose -f compose-dev.yml restart web
```

**pgweb** (DB browser) — http://localhost:8081, opens straight on the `watchemall`
database (no connection form, no login).
