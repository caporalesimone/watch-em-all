# Developer Rules — Backend (Python)

> Binding for all Python code (core and plugins). Tooling: [build-system](../../infrastructure/build-system.md) · CI: [ci](../../infrastructure/ci.md).

## Style and types

- **BE-1** — Python 3.12+. `ruff check` and `ruff format` clean; `mypy --strict` clean. No `# type: ignore` without a comment explaining why.
- **BE-2** — Type hints **everywhere** (full signatures); `Any` only at the boundary with untyped libraries, never in contracts.
- **BE-3** — Naming: `snake_case` for functions/variables, `PascalCase` for classes, `UPPER_CASE` for constants. Identifiers in English; comments may be in Italian.
- **BE-4** — Short functions at a single level of abstraction; extract before exceeding ~40 lines. No catch-all "manager" classes.

## Models and data

- **BE-5** — **Pydantic v2 at every I/O boundary**: API request/response, payloads persisted as JSON, plugin contracts. Never untyped dicts in public contracts.
- **BE-6** — **Prices always `Decimal`**, never float. JSON serialization: Decimal as a string, datetime ISO-8601 **UTC**.
- **BE-7** — SQLAlchemy: queries always filtered by the token's `user_id` in operational tables (multi-tenancy: DB-R1); uniqueness constraints declared in the schema, not just "guaranteed by the code".
- **BE-8** — No SQL in strings formatted with external input: bound parameters only.

## Errors and logging

- **BE-9** — Specific exceptions, never a silent `except Exception`: either handle it, re-raise it, or log it with context. Runs (scrape/alert/summary) catch at the boundary and record in the system logs.
- **BE-10** — Logs: actionable messages with identifiers (user_id, plugin_id, run_id), **never users' operational content** (product titles, notification payloads) in the `system_log`.
- **BE-11** — API errors follow the `{detail, code}` format and the statuses of the [conventions](../../api/README.md).

## Concurrency and time

- **BE-12** — No thread/process spawn outside the [Scraper Runner](../../4-capabilities/core/scraper-pool.md); concurrency is a property of the system, not of the features — and between scrapers there is none: execution is serial (SCHED-R6).
- **BE-13** — `datetime.now(tz=UTC)` or the injectable application clock; never naïve `utcnow()`. Persisted timestamps are **UTC**; entered times (slots, alerts) are interpreted in the **configured timezone** (`TZ`, default `Europe/Rome`) with explicit conversions via `zoneinfo` — never rely on the process's implicit local time. One timezone per installation.
- **BE-14** — Deterministic hashes (SHA-256) for any persisted identity; **never** the built-in `hash()`.
- **BE-21** — **Synchronous backend.** `def` endpoints (run by FastAPI in its threadpool), classic SQLAlchemy `Session`, psycopg in synchronous mode; **no `async def`/asyncio** in the core or in the plugins (the plugin-contract methods — `run_for_user`, `send`, `run_test` — are synchronous, and `context.http` is a synchronous client). Concurrency lives **only** where it is a property of the system: the web threadpool and the worker's [thread runner](../../4-capabilities/core/scraper-pool.md). A choice declared for the ≤5-10 users posture: at this scale async gives no throughput and would complicate the runner, the advisory locks and the plugin contract; scaling is done by tuning the threadpool and the connection pool, and evolving towards async/parallelism is a [future improvement](../../future-improvements/README.md) if the project grows. The dispatcher stays non-blocking by queueing to the runner (CRON-R5), not with asyncio.

## Tests

- **BE-15** — Pure logic (delta, alert diff, thresholds, due slots) covered by **tabular unit tests**: they are the heart of the product's correctness.
- **BE-16** — Integration on an ephemeral Postgres (the CI provides the service) for catalog update, auth, cascades.
- **BE-17** — Tests never touch the network: saved fixtures; the context's HTTP client is faked.
- **BE-18** — A fixed bug = a test that would have caught it.

## API

- **BE-19** — Router with `tags`, Pydantic models for request/response (the Swagger is complete by construction), the endpoint registered in [endpoints.md](../../api/endpoints.md) **before** its implementation.
- **BE-20** — User endpoints: the implicit id is the token's; someone else's resources → `404`. Admin endpoints: `require_admin`, never users' operational data.
