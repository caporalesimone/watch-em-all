# System logs and maintenance (admin)

> **Layer 3 — Admin feature** · Audience: architects, developers · Text + Mermaid, no code.

## System logs

The record of the system's operational events, viewable in near-real-time from the admin page (incremental polling with a cursor, pausable auto-scroll, filters by level and source).

- **LOG-R1** — **Implemented** sources: `worker` (dispatcher: runs, recoveries, skips due to overlap, daily maintenance — purge of logs/runs past retention) and `scraper` (events emitted by scraper plugins via the context logger). Only `wea.worker.*` and `wea.plugin.*` records are persisted; everything else stays on stdout. The `alert`/`summary` sources arrive with notifications/summary (phase 6+). Levels: `info`, `warning`, `error`.
- **LOG-R2** — Notable events that are always recorded: run executed (with its delay relative to the slot; beyond the threshold → "recovery" warning), slot skipped due to overlap (warning), run error/timeout (error). **No heartbeat row** (2026-06-26 decision): worker liveness stays on `/api/health` + a heartbeat file, not a recurring log line.
- **LOG-R3** — Polling uses a cursor (id of the last row seen): the server returns only the rows that follow it.
- **LOG-R4** — Messages never contain users' operational content (product titles, notification content): only identifiers and metrics — consistent with the principle that the admin does not read users' data.

## System logs page (4.F3/4.F4)

A top-level admin entry **`/admin/logs`**, **hybrid** model: **Live ON** = cursor tail (`GET /api/admin/logs?since=<maxId>`, auto-refresh ~5 s, pagination hidden); **Live OFF** = paged **history** (`GET /api/admin/logs/page?page=&size=` → `{items, total, counts, sources}`). Filters: **level tabs with counts** (All/INFO/WARN/ERR), **multi-source chips** (dynamic from the sources present — today worker/scraper), message **search** `q` (ILIKE), **rows per page** 25/50/100. Table time · source · level · message + a **`{ }`** button that opens the row's `context_json` in a modal.

## Maintenance and global settings

- **MNT-R1** — **Alert history purge**: a global rule by date ("delete all users' notifications older than X / older than N days"), applied without accessing the content.
- **MNT-R2** — **Automatic retention of operational logs**: system logs and run records are cleaned automatically beyond the configured window (default 90 days). The **price history has no retention**: it is the system's value and is kept forever.
- **MNT-R3** — **System settings** editable from the UI without a restart: `scraper_run_timeout_min`, the recovery delay threshold (`catchup_warning_min`), retention days (`log_retention_days`), the user-deletion grace period (`user_deletion_retention_days`). Persisted in the DB (DB-first config), with safe defaults on first startup. **Implemented (4.F7)**: an **Admin → Settings** page (`/admin/settings`, top-level with *Feature flags* nested under it) via `GET`/`PATCH /api/admin/settings` (known keys, ranges validated → 422); the worker re-reads the values on each run/purge.
- **MNT-R4** — **Health**: the app exposes a liveness check (application + DB reachability) used by container monitoring; the worker is supervised via heartbeat ([scraper-monitoring](../../../docs-ita/3-features/admin/scraper-monitoring.md)).
- **MNT-R5** — **Backup**: backup/export/restore scripts versioned in the repo (`ops/`), shipped with the `ops` image and run by hand as an ephemeral container; the archive includes a full dump (data + DB-first configurations) and local bootstrap files ([backup-and-restore](../../infrastructure/backup-and-restore.md)). The price history cannot be reconstructed: the host decides the cadence.

## Overview

```mermaid
flowchart LR
    subgraph "Sources"
        W[Worker: runs, recoveries,<br/>skips, maintenance]
        S[Scraper plugins: logger]
        AE[Alert/Summary engine]
    end
    subgraph "Persistence"
        SL[(System logs)]
        RUNS[(Run records)]
    end
    subgraph "Admin page"
        LIVE[Near-real-time logs<br/>filters + cursor]
        STATS[Scraper statistics]
        SET[Global settings]
        PURGE[Alert history purge]
    end
    W & S & AE --> SL --> LIVE
    W --> RUNS --> STATS
    RET[Automatic retention] -.cleans.-> SL & RUNS
    SET -.configures.-> RET
```
