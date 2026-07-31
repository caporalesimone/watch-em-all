# Schema compatibility (core)

> **Layer 4 — Capability** · Audience: developer, operator.
>
> Limited to what is implemented (DOC-12). Covers the startup drift guard (4.B0) and what each process does when the database does not match the running code.

## Purpose

Before 1.0 the schema is **not migrated**: it changes freely and the database is recreated ([data-and-multitenancy](../../2-architecture/data-and-multitenancy.md)). "New containers on an old database" is therefore an ordinary event, not an exotic one — and the failure it produces is the worst kind, because `create_all` creates missing tables and **never alters existing ones**. The application comes up believing a schema it does not have.

This capability makes that state **legible and inert**: detected once at startup, said in one place, and acted on identically by both processes.

## What the guard sees

Run at startup, after the schema is ensured (`create_schema` + each plugin's `initialize`), over the core metadata and every plugin's own (DB-R7). Three findings, all of which mean the application cannot work against this database:

| Finding | Why it is fatal |
|---|---|
| A **table** in the model, absent from the DB | nothing that touches it can run |
| A **column** in the model, absent from the DB | the phase-3 incidents (`products.brand/tags`); `create_all` cannot add it |
| A column the **DB requires** (`NOT NULL`, no default) that the model no longer writes | every `INSERT` is rejected: the model does not supply a value |

The third is the mirror image of the second and was added in 0.9.0 with the page below, because it is the half that a *new* version produces. On a 0.8.0 database, 0.9.0 reported the missing `price_history` columns and said nothing about the leftover `NOT NULL` columns that break adding a watch — three scattered symptoms with only one of them explained.

A leftover column the DB does **not** require is deliberately **not** reported. A nullable one, or one with a server default, sits there unread and costs nothing; reporting it would take the application down for something that breaks nothing. Everything reported here is treated as an incompatibility, so the bar for reporting is "the application cannot work", not "the schemas differ".

Out of scope, still: column types, nullability of model columns, indexes. This is an alarm, not a migration tool.

## Requirements

- **INC-R1** — While drift is present the **web serves an incompatibility page in place of every page and every API route**. It does not refuse to start. A container that exits leaves nothing to read but `docker logs`, and under a restart policy it exits in a loop — the operator sees a dead service and has to go digging for the reason. One that stays up explains itself at the URL they already had open: which tables disagree, which version is running, and what to do. What it replaces is worse than either: a scattering of HTTP 500s from whichever page happens to touch the wrong table first, with the cause in a startup log nobody re-reads.
- **INC-R2** — An `/api/` route answers **`503` with JSON** (`{code: "schema_incompatible", detail, findings, version}`), everything else `503` with the HTML page. The SPA and any script get something they can read instead of a page they cannot parse; `503` is both true and unambiguous to a monitor.
- **INC-R3** — **`GET /api/health` stays reachable**, and it is the only exception. It is what a monitor polls and what an operator curls; blocking it would turn a legible failure into an unreachable service, which is the thing the page exists to avoid.
- **INC-R4** — The **worker suspends its scheduled work** — no scrapes, no channel deliveries — and keeps its **heartbeat**. It has no user to explain itself to, and unlike a page it *writes*: a run against a schema it does not agree with would fail halfway through, on a database somebody may still be able to salvage. The heartbeat continues so a silent worker does not read as a second, different fault.
- **INC-R5** — The page is **self-contained**: inline CSS, no asset, no template engine, no i18n lookup. It has to render when the database is unusable, so anything it had to fetch first is one more thing that can fail at the worst moment. It is operator-facing and stays in English, like the logs. Table and column names are **escaped**: they come from a database the process does not control.
- **INC-R6** — The state is read from `app.state.schema_drift`, filled by the lifespan **before the first request is served**, so there is no window in which a mismatched database is reachable. The check itself never blocks startup: a check that fails is logged and treated as no drift, because a guard that can take the application down when *it* breaks is worse than the thing it guards against.

## The remedy the page states

Pre-1.0, recreate the database — `docker compose -f compose-dev.yml down -v`, then up again. If the data matters: restore a backup taken with the previous version, or go back to that version. **Nothing has been modified**, which is the whole point of stopping before the first write.

## References

[env-variables](../../env-variables.md) (`WEA_SCHEMA_DRIFT_ALERT`, which gates only the admin errors feed) · [endpoints](../../api/endpoints.md) · [data-and-multitenancy](../../2-architecture/data-and-multitenancy.md) · [cron-worker](cron-worker.md)
