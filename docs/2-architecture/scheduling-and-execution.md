# Scraper scheduling and execution

> **Layer 2 — Architecture** · Audience: SW architects, system engineers · Text + Mermaid, no code.

## The three scheduled flows

There is no single cron table: the three flows have different owners, granularities, and logics, and they are **deliberately decoupled** (the scrape updates the data; the notification arrives when the user wants it).

| Flow | Owner | Granularity | Frequency |
|---|---|---|---|
| **Scrape** | Admin | Per-scraper | **1..N slots per day** (a list of times per scraper) |
| **Alert** | User | Per-account | Chosen days of the week + a single time |
| **Summary** | User | Per-account | Weekly (chosen day) or monthly (day 1), opt-in |

## The dispatcher (Cron Worker)

The worker wakes up every minute and compares the current time against the schedules. The "due" principle: a job is due when there is a **scheduled slot already in the past** that has not yet been executed. This gives **catch-up** for free: if the worker was down, on restart it runs the most recent missed slot — **only one**, never a replay of all the backlogged slots.

```mermaid
flowchart TD
    T[Tick: every minute] --> S{For each scraper:<br/>last due slot > last executed?}
    S -- yes --> RUN[Enqueue to the serial runner<br/>if not already queued/running]
    S -- no --> A
    RUN --> A{For each user:<br/>alert due today?}
    A -- yes --> AE[Run Alert Engine]
    A --> SU{For each user:<br/>summary due?}
    SU -- yes --> SM[Run Summary]
    SU --> HB[Heartbeat + back to tick]
```

Honest limits of catch-up (declared, a hobby-project choice):

- **Scraper**: catch-up crosses midnight (*slots* are compared, not dates) — a scraper down since 23:00 recovers the 23:50:00 slot even at 1 a.m.
- **Alert and summary**: catch-up applies **within the day it is due**. If the system stays down for the entire due day, that notification is skipped and the events will flow into the next one (the diff is cumulative by nature: nothing is lost in the content, only in the moment of delivery).

## The serial runner

Scrapers **do not run inside the dispatcher**: they are enqueued to a runner that executes them **one at a time**, in order of arrival. There is no concurrent execution between scrapers: each scraper has its **own independent schedule**, and the admin distributes the slots across the day with the help of the [calendar view](../3-features/admin/scraper-scheduling-and-limits.md) (read-only, one click takes you to the scraper's configuration).

```mermaid
graph TB
    subgraph "Worker"
        D[Dispatcher<br/>ticks every minute, never blocked]
        Q[FIFO queue of due jobs]
        J1[Runner: ONE job at a time<br/>single-thread scraper]
    end
    D --> Q --> J1
```

Architectural rules (the full rationale in [3-features/admin/scraper-scheduling-and-limits.md](../3-features/admin/scraper-scheduling-and-limits.md)):

1. **Every scraper is intrinsically single-thread**: a single workflow that reads a site calmly, one request at a time, with configurable pauses. It is a property of the contract, not an option.
2. **No concurrent execution between scrapers**: the runner executes **one at a time**; two slots that fall in the same minute run in sequence (FIFO queue). Per-scraper independent schedules, well distributed, make the queue the exception, not the rule.
3. **Never two runs of the same scraper together**: a per-scraper lock at the database level, valid even across containers (worker and web, for on-demand scrapes).
4. **Mandatory politeness**: the HTTP client provided to plugins enforces a minimum delay between requests to the same site (configurable per scraper by the admin). The system **must never** flood or resemble a DoS: few requests, slow, identifiable.
5. **Run timeout**: a run that exceeds the maximum time (admin) is terminated and marked as error — a hung scraper does not block the system.

## The scrape cache

Before each search the scraper — through the context's HTTP client, transparently to it — checks whether there is **a recent cached result for the same query**: if the configured **half-life** has not expired, it reuses the data and avoids the call to the site; otherwise it performs the scrape and stores the result. At the start of each run the plugin's expired records are deleted. The cache lives in a **dedicated table** ([schema](../4-capabilities/database/schema.md), `scrape_cache`), the half-life is configurable by the admin **per plugin**, and the plugin's admin page offers a **manual purge** button.

It is an optimization with a double effect: **across different users in the same run** (two users watching the same category cost a single visit to the site) and **across different runs** close together within the half-life. Contract details: [plugin-context](../4-capabilities/core/plugin-context.md), CTX-R9.

## Observability of executions

Every run produces an **execution record** (actual duration, products found/new/changed/disappeared, HTTP requests made, cache reuses, outcome) with the **per-user detail**; operational events (executions, catch-ups, skips due to overlap, errors, heartbeats) end up in the system log, viewable by the admin in near-real-time. It is the basis of the [admin reporting](../3-features/admin/scraper-monitoring.md).

```mermaid
sequenceDiagram
    participant D as Dispatcher
    participant P as Runner
    participant S as Scraper
    participant DB as DB

    D->>P: job (scraper, slot) — queued, one at a time
    P->>DB: per-scraper lock? yes
    P->>DB: delete the plugin's expired cache
    P->>DB: open scrape_run (slot, trigger)
    loop for each configured user
        P->>S: run_for_user(user)
        S->>DB: valid cached query? reuse : scrape + store
        S->>DB: products via update_catalog
        P->>DB: per-user detail row
    end
    P->>DB: close scrape_run (outcome, counters, duration)
    P->>DB: release lock + system_log
```

## Temporal assumptions (V1)

- Granularity at the **minute**; the times entered are interpreted in the **installation's configured timezone** (`TZ`, default `Europe/Rome` — [configuration](../infrastructure/configuration.md)), the persisted timestamps remain in UTC.
- **A single timezone** for the whole installation, configurable but not per-user (per-user multi-timezone: [future improvement](../future-improvements/README.md)).
- Daylight saving time transitions may shift the perception of a slot by one hour twice a year: accepted and documented, with no special handling.
