# The administrator's experience

> **Layer 1 — Business / UX** · Audience: everyone · Descriptive text only.
>
> English mirror of the Italian reference [`docs-ita/1-business/admin-experience.md`](../../docs-ita/1-business/admin-experience.md), limited to what is implemented (DOC-12). It tells the realized journey: first startup, creating users (create + list), governing the scrapers, watching the system log, and maintenance/global settings. The parts that depend on not-yet-built capabilities — the full account lifecycle (disable, reset, deferred deletion, filters), scraper statistics, the load dashboard, notification-channel configuration, and messaging users — stay in the Italian document. The functional details are in the [Layer 3 — admin features](../3-features/admin/).

## First startup

The administrator installs the system (one command, see the [infrastructure](../infrastructure/deployment.md) docs) and logs in with the admin account created automatically at first startup; the system immediately forces the temporary password to be changed. From here on, the administration area is home.

## Creating the users

There is no self-registration: it is the admin who creates each account, assigning a username, first and last name, a role, and a temporary password that the user will have to change at first login. A duplicate username is refused. The list shows each user's username, name, role, status and **last login**.

*(The richer account management — disable, reset password, deferred deletion with a grace period, status filters and courtesy notifications — arrives in a later phase.)*

## Governing the scrapers

The most important responsibility. For each installed scraper the admin decides:

- **How many times a day and at what time** the scraper runs: from one to several daily executions, each at a chosen time, **independent of the other scrapers'**. A shop with flash prices can run three times a day; a static one, just once. Scrapers never work in parallel with one another: each runs at its own time, one at a time, calmly, one site at a time. The house rule is firm: **never hammer a site** — no bursts, no dozens of simultaneous requests.
- To spread the times out well, the admin has a **day calendar view**: all the scheduled executions of all scrapers at a glance, read-only; a click on a scraper takes you to its configuration page.
- **The operational parameters** of each scraper (wait times, client identification, the site's discount rules, cache duration), from the configuration page each plugin provides.
- The **scrape cache**: if two users observe the same thing, or two close-together executions repeat the same search, the system reuses the freshly gathered data instead of going back to the site. The admin decides, per scraper, how long the data stays "fresh" and can flush the cache with a button.
- The optional **kill switch**: a scraper can be suspended without uninstalling it.

## Watching the work

The admin has the **system log** in near-real-time: executions, recoveries after a downtime, executions skipped because the previous one was still in progress, errors — with filters by severity and by source, a live tail and a paged history. A **liveness signal** of the scheduling engine is exposed too (worker heartbeat on the health check): if the component that orchestrates the executions stops, the admin can tell.

## Maintenance

- **Global settings**, editable from the UI without a restart: the maximum duration of an execution, the recovery lateness threshold, log retention, and the grace period before deleted accounts are removed.
- **Automatic retention** of operational data: system logs and run records are cleaned automatically beyond the configured window. The price history is kept forever.
- **System health**: a liveness check exposed by the application and the state of the containers; for direct inspection of the data in development there is a dedicated tool (pgweb), never active in production.

## What the admin cannot do

The admin does not see the users' carts or catalogs. The admin configures the system, not the contents. If a user needs help, the admin helps by guiding them — not by entering their data.
