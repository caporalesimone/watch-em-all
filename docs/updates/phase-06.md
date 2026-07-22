# Phase 6 — In-app alerts

> Feature-level recap. Phase 6 turns the carts into a **notification engine**, delivered for now
> **in-app only**: you pick which changes matter on each cart, and **right after every scrape** the
> system compares each cart against a **baseline** and drops a single readable **digest** into a
> new **Alerts** section — what changed, old → new price, where it's from, threshold state — with an
> **unread badge** in the sidebar. No scheduling to configure — it's **event-driven**. The external
> channels (email, Discord) come later; keeping them separate makes this phase small and verifiable.

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

### 3) Event-driven — right after each scrape

- There's **nothing to schedule**. Whenever a scrape updates your catalog — the automatic scheduled
  run, an on-demand scrape-now, or the TP test generator's **Simulate scrape** — the engine runs for
  the affected users immediately. So an alert lands **seconds after** the price change that caused it,
  and manual testing is instant.

### 4) One digest per run

- Each scrape run collects every cart of yours that changed into a **single aggregated digest** —
  never one message per cart. Each digest is **self-sufficient**: per product the event tags, previous
  and current price, discount, **provenance** (which store), and a link; per cart the totals and
  threshold state. It is always written to the in-app history.

### 5) The Alerts history + unread badge

- A new **Alerts** section lists your notifications newest-first (paginated), each row showing when
  it was generated, how many carts changed, and an **unread** marker. Opening one shows the full,
  readable digest (tags as graphic badges) and **marks it read**. You can **select multiple and
  delete** them. The sidebar carries an **unread count** badge that stays **live** (it polls every
  20s), so a new alert shows up without a reload.

_Under the hood:_ three new tables (`cart_alert_types`, `alert_snapshot`, `alert_log`) and the
`src/core/alert_engine.py` module (baseline seed/advance/delete, the product and cart-event diffs,
and `run_for_user` which aggregates one `AlertEvent` per user and writes it to `alert_log`). The run
is **triggered by the scrape**: the worker runs it after a scheduled scrape for the users it touched,
and the web runs it right after a scrape-now / TP simulate (`src/web/adjust.run_user_alerts`) — no
time-cadence, no `alert_schedule`. The API adds `PUT /api/carts/{id}/alert-types` and the
`/api/alerts` history (list, detail, mark-read, unread-count). Delivery to external channels — the
`alert_delivery` table and the dispatch to notifiers — is deliberately deferred to phase 7 (and will
be **asynchronous**: pending rows drained by the worker); here the digest only lands in the history.

## Good to know

- **In-app only this phase.** Alerts land in the Alert History; email/Discord delivery arrives in
  later phases. A notification is always recorded in the history even with no channels configured.
- **First run is silent.** Enabling alert types seeds the baseline from the current state; the first
  run after that produces no notification (nothing has changed yet).
- **All-time-low is not here.** The "lowest price ever" tag depends on price analytics, which lands
  in phase 11.
- Easiest way to try it: on the **TP Scraper** page enable an alert type on a cart, **edit** a
  product's price/availability, then press **Simulate scrape** — the digest appears at once.

## Useful Commands

```bash
docker compose -f compose-dev.yml up -d --build         # db + web + worker + pgweb (DB browser on :8081)
docker compose -f compose-dev.yml down -v               # reset the DB (admin recreated from .env)

# A quick end-to-end (user token required):
#   PUT   /api/carts/{id}/alert-types   {"alert_types":["PRODUCT_ON_SALE"]}   # seeds the baseline
#   …edit a TP product's price, then POST /api/plugins/tp-scraper/scrape — the scrape runs the
#    alert engine for you and writes the digest…
#   GET   /api/alerts                   # the history (paginated)
#   GET   /api/alerts/unread-count      # the sidebar badge
#   GET   /api/alerts/{id}              # the full digest
#   POST  /api/alerts/{id}/read         # mark read
#   DELETE /api/alerts                  {"ids":[1,2]}   # bulk delete
```

**pgweb** (DB browser) — http://localhost:8081. New tables to inspect this phase:
`cart_alert_types`, `alert_snapshot`, `alert_log`.
