# Phase 6 — In-app alerts

> Feature-level recap. Phase 6 turns the carts into a **notification engine**, delivered for now
> **in-app only**: you pick which changes matter on each cart, the system compares every run
> against a **baseline** and, at the cadence you choose, drops a single readable **digest** into an
> **Alert History** — what changed, old/new prices, where it's from, threshold state — with an
> **unread badge** in the dashboard. The external channels (email, Discord) come later; keeping them
> separate makes this phase small and verifiable.

## What's implemented (0.6.0)

<!-- Filled in as each sub-phase ships. Keep it feature-level and user-facing. -->

### 1) Per-cart alert types

<!-- 6.B1 / 6.F1: choose which events matter on each cart; enabling the first type seeds the baseline. -->

### 2) The baseline — diff, not state

<!-- 6.B2 / 6.B3: one snapshot per (user, cart); seed on enable, advance every run, delete on disable / cadence off; re-seed on cadence on. First run is silent. -->

### 3) What counts as a change

<!-- 6.B4 / 6.B5: product tags (on sale / off sale / unavailable / available again) and cart events (all on sale / threshold reached / threshold reached partial), each only for the types enabled on that cart. -->

### 4) One digest per run

<!-- 6.B6: all carts with events aggregate into a single AlertEvent per user, always written to the in-app history. -->

### 5) Your cadence

<!-- 6.B7 / 6.F2: pick the weekdays and time in your Profile; the worker runs the alert engine only when due, with same-day catch-up if it was down. -->

### 6) The Alert History

<!-- 6.B8 / 6.F3 / 6.F4: a paginated, mailbox-style list with a readable digest detail, read/unread state and an unread badge in the dashboard. -->

_Under the hood:_
<!-- tables opened this phase (cart_alert_types, alert_snapshot, alert_schedule, alert_log), the core
alert engine module, the worker trigger, and the /api/alerts + alert-schedule API. Delivery to
external channels (alert_delivery, dispatch) is deferred to phase 7. -->

## Good to know

- **In-app only this phase.** Alerts land in the Alert History; email/Discord delivery arrives in
  later phases. A notification is always recorded in the history even with no channels configured.
- **First run is silent.** Enabling alert types seeds the baseline from the current state; the first
  run after that produces no notification (nothing has changed yet).
- **All-time-low is not here.** The "lowest price ever" tag depends on price analytics, which lands
  in phase 11.

## Useful Commands

```bash
docker compose -f compose-dev.yml up -d --build         # db + web + worker + pgweb (DB browser on :8081)
docker compose -f compose-dev.yml down -v               # reset the DB (admin recreated from .env)
```

<!-- Fill in the concrete API calls (enable alert types, set cadence, read the history) as they ship. -->

**pgweb** (DB browser) — http://localhost:8081. New tables to inspect this phase:
`cart_alert_types`, `alert_snapshot`, `alert_schedule`, `alert_log`.
