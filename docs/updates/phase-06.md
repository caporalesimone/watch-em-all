# Phase 6 — In-app alerts

> Feature-level recap. Phase 6 turns the carts into a **notification engine**, delivered for now
> **in-app only**: you pick which changes matter on each cart, the system compares every run
> against a **baseline** and, at the cadence you choose, drops a single readable **digest** into a
> new **Alerts** section — what changed, old → new price, where it's from, threshold state — with an
> **unread badge** in the sidebar. The external channels (email, Discord) come later; keeping them
> separate makes this phase small and verifiable.

## What's implemented (0.6.0)

### 1) Per-cart alert types

- On a cart's detail page you choose which changes should notify you: a product goes **on sale** /
  its **discount ends** / goes **out of stock** / is **back in stock**, the **whole cart goes on
  sale**, or the **savings threshold is reached**. Default: nothing enabled.
- Enabling the **first** type **seeds the baseline** (a reference snapshot of the cart's current
  state); disabling them **all** deletes it. The UI notes that changing the selection **restarts
  monitoring from now** — you're told about future changes, not past ones.

### 2) The baseline — diff, not state

- One snapshot per **(user, cart)** records, for each product, whether it's on sale, available and
  its current price, plus the cart-level "all on sale" and "threshold reached" flags. Every run
  diffs against it and then advances it, so you're notified **only about what changed** since the
  last look — never the same state repeated, and no backlog when you switch things on and off.
- The **first run after enabling is silent** (nothing has changed against a just-taken baseline);
  delisted products are ignored; a product newly added to an active cart is seeded silently.

### 3) One digest per run

- At your alert time the engine collects every cart with changes into a **single digest** — never
  one message per cart. Each digest is **self-sufficient**: per product the event tags, previous and
  current price, discount, **provenance** (which store), and a link; per cart the totals and
  threshold state. It is always written to the in-app history.

### 4) Your cadence

- In **Profile → Alert cadence** you set the **weekdays** and the **time** you want to be told (all
  days = daily, none = off). The worker runs the engine only when due, with **same-day catch-up** if
  it was down at the time (a single run, never a flood). Turning the cadence **off** clears your
  baselines; turning it **on** re-seeds them from the current state — the app tells you which
  happened.

### 5) The Alerts history + unread badge

- A new **Alerts** section lists your notifications newest-first (paginated), each row showing when
  it was generated, how many carts changed, and an **unread** marker. Opening one shows the full,
  readable digest and **marks it read**. The sidebar carries an **unread count** badge.

_Under the hood:_ four new tables (`cart_alert_types`, `alert_snapshot`, `alert_schedule`,
`alert_log`) and the `src/core/alert_engine.py` module (baseline seed/advance/delete, the product
and cart-event diffs, and `run_for_user` which aggregates one `AlertEvent` per user and writes it to
`alert_log`). The cadence lives in `src/core/alert_cadence.py`; the worker dispatches a synchronous
alert run per due user each tick, mirroring the scraper dispatcher. The API adds
`GET/PUT /api/me/alert-schedule`, `PUT /api/carts/{id}/alert-types` and the `/api/alerts` history
(list, detail, mark-read, unread-count). Delivery to external channels — the `alert_delivery` table
and the dispatch to notifiers — is deliberately deferred to phase 7; here the digest only lands in
the history.

## Good to know

- **In-app only this phase.** Alerts land in the Alert History; email/Discord delivery arrives in
  later phases. A notification is always recorded in the history even with no channels configured.
- **First run is silent.** Enabling alert types seeds the baseline from the current state; the first
  run after that produces no notification (nothing has changed yet).
- **All-time-low is not here.** The "lowest price ever" tag depends on price analytics, which lands
  in phase 11.
- Use the **TP Scraper** page to add products, and drop a price (or use a real Dragon Store scrape)
  to see a digest appear at your next cadence run.

## Useful Commands

```bash
docker compose -f compose-dev.yml up -d --build         # db + web + worker + pgweb (DB browser on :8081)
docker compose -f compose-dev.yml down -v               # reset the DB (admin recreated from .env)

# A quick end-to-end (user token required):
#   PUT   /api/carts/{id}/alert-types   {"alert_types":["PRODUCT_ON_SALE"]}   # seeds the baseline
#   PUT   /api/me/alert-schedule        {"scheduled_time":"09:00","weekdays":[0,1,2,3,4,5,6]}
#   …a scrape (or a price change) then a due cadence run writes the digest…
#   GET   /api/alerts                   # the history (paginated)
#   GET   /api/alerts/unread-count      # the dashboard badge
#   GET   /api/alerts/{id}              # the full digest
#   POST  /api/alerts/{id}/read         # mark read

# Speed up the worker tick while testing (admin token):
#   PATCH /api/admin/feature-flags      {"worker_tick":{"seconds":3}}
```

**pgweb** (DB browser) — http://localhost:8081. New tables to inspect this phase:
`cart_alert_types`, `alert_snapshot`, `alert_schedule`, `alert_log`.
