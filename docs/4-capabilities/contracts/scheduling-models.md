# Contracts — Scheduling and monitoring models

> **Layer 4 — Contract** · Audience: developer · Pseudocode allowed. Feature: [scraper-scheduling-and-limits](../../3-features/admin/scraper-scheduling-and-limits.md), [scraper-monitoring](../../../docs-ita/3-features/admin/scraper-monitoring.md).

Three schedules with different owners plus the global settings, read by the dispatcher; scheduled scraper runs produce the execution records:

```mermaid
flowchart TB
    subgraph ADM["Admin"]
        SS[ScraperSchedule<br/>times[], enabled, last_slot]
        SET[SystemSettings<br/>timeout · retention · deletion grace]
    end
    subgraph USR["Per-user"]
        AS[AlertSchedule<br/>weekdays, time, last_run_date]
        SC[SummaryConfig<br/>weekly/monthly, last_run_date]
    end
    CRON[Cron Worker<br/>tick/min] --> SS & AS & SC
    SS --> REC[ScrapeRun + ScrapeUserLog<br/>execution records]
```

## Schedules

```python
# Scrape — admin, per-scraper, 1..N slots per day
class ScraperSchedule(BaseModel):
    scraper_id: str                    # = the scraper's plugin_id
    times: list[str]                   # 1..N canonical times (slots) "HH:MM:SS" (4.F1); input
                                       # accepted as "HH:MM" or "HH:MM:SS"; sorted, unique
    enabled: bool = True               # runtime suspension without touching the manifest
    last_slot: datetime | None = None  # last EXECUTED slot (datetime, not date:
                                       # supports N slots/day and cross-midnight catch-up)

# Alert — per-user: calendar cadence
class AlertSchedule(BaseModel):
    user_id: int
    scheduled_time: time
    weekdays: list[int] = []           # 0=Mon..6=Sun (Python date.weekday() convention;
                                       # ⚠ JS Date.getDay() starts on Sunday: the UI maps it)
                                       # [] = off · 7 days = daily
    last_run_date: date | None = None  # anti-duplicate guard + intra-day catch-up

# Summary — per-user: see SummaryConfig in core/summary-report.md
```

## System settings (admin, runtime)

```python
class SystemSettings(BaseModel):       # persisted in system_settings (key-value), editable from the UI
    scraper_run_timeout_min: int = 30  # beyond this → run terminated, status "timeout"
    catchup_warning_min: int = 10      # delay beyond which an execution is logged as a catch-up
    log_retention_days: int = 90       # system_log + scrape_run/scrape_user_log
    user_deletion_retention_days: int = 30  # grace period before the automatic purge (USR-R9);
                                       # the deadline is fixed at marking time: changes apply only going forward
```

## Execution records (monitoring)

```python
class ScrapeRun(BaseModel):            # ONE row per scraper run
    run_id: int
    scraper_id: str
    trigger: Literal["scheduled", "manual"]    # manual = scrape-now
    slot: datetime | None              # the scheduled slot (None if manual)
    started_at: datetime
    finished_at: datetime | None
    status: Literal["running", "ok", "partial", "error", "timeout"]
    # ok = all users ok · partial = at least one user ok and one failed
    # error = no user completed · timeout = terminated by the system
    users_processed: int
    products_found: int
    products_new: int
    price_changes: int
    products_removed: int
    products_excluded: int             # exclusions decided by the plugin (NOT the out-of-stock ones)
    http_requests: int                 # counted by the core client (only real requests to the site)
    cache_hits: int                    # requests served from the scrape cache (CTX-R9)
    error_message: str | None

class ScrapeUserLog(BaseModel):        # ONE row per user per run
    run_id: int
    user_id: int
    started_at: datetime
    finished_at: datetime | None
    products_found: int
    products_new: int
    price_changes: int
    http_requests: int                 # the run's share attributed to this user
    cache_hits: int                    # likewise, reuses from the cache
    status: Literal["ok", "error"]
    error_message: str | None
```

Normative notes:

- The **run duration** is `finished_at − started_at` of the run record (wall-clock), never the sum of the per-user times.
- The per-user detail is the basis of the admin drill-down ("who generates the load").
- Retention: `scrape_run`/`scrape_user_log` and `system_log` follow `log_retention_days`; the schedules do not.
