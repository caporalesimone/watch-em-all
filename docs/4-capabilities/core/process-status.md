# Process status (core)

> **Layer 4 — Capability** · Audience: developer, operator.
>
> Limited to what is implemented (DOC-12). What each process of an installation reports about itself, and who reads it.

## Purpose

The web and the worker share **nothing but the database**, so it is the only place either can report on itself to the other. `process_status` is that place: one row per process, saying when it last spoke and what it is doing.

It is named for the question, not for its first answer. A table called `worker_heartbeat` would have had to be replaced the first time anything else needed reporting; "who reports" is a name here, not a schema change.

## What it replaced

`GET /api/health` carried `worker_heartbeat_age_s` from phase 1 and it was **hardcoded `null`** — a placeholder phase 4 was meant to fill and did not. Meanwhile the worker *was* beating: it writes `/tmp/worker-heartbeat` every tick (CRON-R7), which the container's own healthcheck reads (`unhealthy` past 180s). That file lives in the worker's own tmpfs, so nothing outside that container can see it.

So the two halves never met: `docker compose ps` said `healthy` while the API said `null`, and an operator comparing them had two answers to one question. The file stays — it is the right mechanism for a container healthcheck — and the row is the half the web can read.

## Requirements

- **PST-R1** — One row per process, keyed by a **name** (`worker`, and whatever reports next), **updated in place**. A heartbeat is a *state*, not an event: the only question asked of it is "is this alive now", answered by the latest value. Appended it would be ~525.000 rows a year at the default tick — and 86.400 a **day** at the tick's 1s floor — accumulated to answer a question that reads exactly one of them, and then needing a retention policy of their own.
- **PST-R2** — The writer **rate-limits itself**: at most one persisted beat every `MIN_HEARTBEAT_INTERVAL_S` (**30 s**), skipped in memory without touching the database. The tick interval is a feature flag whose floor is 1 s, which is right for scheduling responsiveness and wrong for persistence — a developer lowering it to watch something happen must not turn that into a write per second, for ever. 30 s is chosen against what *reads* the value, not against what the database could survive: the container healthcheck calls the worker unhealthy at 180 s, so this leaves 6× headroom and a skipped beat never reads as a fault, while nobody asks about liveness with sub-minute precision. A **change of state** bypasses the limit — news is not a repetition.
- **PST-R3** — `GET /api/health` reports `worker_heartbeat_age_s`, the seconds since the worker last spoke. `null` now means exactly one thing: it has not reported since this database was created. A failure to read it never fails the probe — a liveness check does not fall over on a secondary signal.
- **PST-R4** — `GET /api/admin/errors` tells three states apart, because they call for different actions: the worker **never reported** (warning — it has not started, or cannot reach the database), it **stopped reporting** past 180 s (error, with the age and the consequence: no scrapes, no deliveries), or it **suspended itself** (error, with the reason it recorded — e.g. an incompatible schema, INC-R4). Not behind `WEA_SCHEMA_DRIFT_ALERT`, unlike schema drift: a worker that is not running is a fault of the installation rather than a development nicety, and its symptom on its own ("my prices are stale") points nowhere. The 180 s threshold is deliberately the container healthcheck's, so the admin page and `docker ps` cannot disagree.
- **PST-R5** — Reporting **never raises**. A process must not die because it could not say that it is alive.

## Shape

```python
class ProcessStatus:          # table: process_status
    process: str              # PK — "worker", "web", …; a name, not an enum
    last_seen_at: datetime    # never more precise than the PST-R2 floor, and does not need to be
    state: str                # "running" | "suspended"
    detail: str | None        # why, when the state calls for it
```

`state` and `detail` are here because the worker already has something true to put in them (it suspends itself on an incompatible schema) **and** a reader for them (the admin errors feed). A column nothing writes and nobody reads is the mistake C7 was about: the room for growth in this table is its name and its key, not empty columns.

## References

[cron-worker](cron-worker.md) (CRON-R7, the heartbeat file) · [schema-compatibility](schema-compatibility.md) (INC-R4, what suspends the worker) · [endpoints](../../api/endpoints.md) · [schema](../database/schema.md)
