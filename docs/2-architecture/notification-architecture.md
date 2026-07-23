# Notification architecture

> **Layer 2 — Architecture** · Audience: SW architects, system engineers · Text + Mermaid, no code.
>
> English mirror of the Italian reference [`docs-ita/2-architecture/notification-architecture.md`](../../docs-ita/2-architecture/notification-architecture.md), limited to what is implemented (DOC-12). Phase 6 ships the **what** (diff against a baseline), the **when** (event-driven, after each scrape) and the **one aggregated digest always written to the in-app history**. Phase 7 adds **delivery to channels** (notifiers, two-level config, per-channel outcome) — including the **in-app channel** itself — documented below. The **periodic summary report** and the **admin notifications / categories** are spec-ahead (phases 10/11) and stay in the Italian reference.

Notifications are the product: everything else in the system exists to reach this moment. The implemented architecture answers three questions: **what** to notify, **when**, and **what remains**.

## What: diff, not state

The system notifies **only what has changed** since the last run, never the current state repeated (no "still on sale" every day). The mechanism is a **baseline**: one reference snapshot per user + cart with active alert types, against which the diff is computed at every run.

```mermaid
stateDiagram-v2
    [*] --> NoBaseline: cart with no active alert types
    NoBaseline --> Baseline: the user enables ≥1 alert type<br/>(silent seed: current state, no notification)
    Baseline --> Baseline: every run → diff vs baseline,<br/>then the baseline advances to the current state
    Baseline --> NoBaseline: all alert types disabled<br/>(baseline deleted)
```

Properties that follow (all intended):

- **First run silent**: right after the alert types are enabled nothing fires (no delta against a freshly seeded baseline).
- **No backlog, no flood**: turning alerts off and on again restarts from "now".
- **Independence from intermediate scrapes**: between two notifications there may be 1 or 10 scrapes; the diff is always "vs the last run". A price that dropped and rose again between two runs produces no noise.
- **New elements without a baseline** (e.g. a product just added to the cart): seeded silently by the first run that meets them.

## When: after each scrape (event-driven)

- *When* to receive: **at the end of a scrape** — the alert engine runs at the end of every scrape that changed the user's catalog (scheduled scrape in the worker, manual scrape-now, the TP's "simulate scrape"). No per-account configuration of days or time. Each scrape run produces **one aggregated digest per user**: a per-cart cadence would make the single aggregated message impossible.
- *What* to receive: **per-cart** — the user chooses the event types that interest them on each cart (sales, availability, threshold…). Default: none active.

## One aggregated digest, always in the history

```mermaid
flowchart TD
    AE[Alert Engine<br/>run at the end of a scrape] --> D{diff non-empty?}
    D -- no --> END[No notification<br/>the baseline advances anyway]
    D -- yes --> DIG[Aggregated digest:<br/>all carts with events,<br/>old/new prices, provenance]
    DIG --> LOG[(Alert history<br/>written ALWAYS)]
```

Design decisions:

1. **One message per run** (`alert_digest`), aggregating all carts with events. Never one notification per cart or per product: a user with 10 carts receives one message, not ten.
2. **The internal history is the primary source**: every notification is recorded **always**, before anything else. No feature depends on any external channel; delivery to notifier channels is an *additional* layer added later (phase 7).
3. **Self-sufficient content**: the digest carries everything needed to decide without opening the app — per product: the event tags, the previous and current price, the discount, the **provenance** (essential in cross carts), the product link; per cart: totals and threshold state.

## Delivery to channels (phase 7)

Writing the digest (cheap) is kept **separate** from delivering it to channels (slow, can fail). When the digest is written, the core records **one `alert_delivery` row per active channel**:

```mermaid
flowchart TD
    LOG[(Digest written<br/>to alert_log)] --> DISP[Per active channel:<br/>one alert_delivery row]
    DISP --> INAPP[in-app: local →<br/>delivered inline]
    DISP --> NET[network channels:<br/>pending]
    NET --> DRAIN{Worker periodic<br/>drain step}
    DRAIN --> OUT[(delivered / failed<br/>per channel)]
```

- **The in-app history is one of the channels.** The `in_app` notifier is a first-class channel: it is **always active for the user** (they cannot switch it off) and its delivery is **local** — the `alert_log` record itself — so it is marked `delivered` inline, never queued. Only an **admin** can disable it globally (kill-switch); while off, the inbox is hidden for everyone. The digest record is still always written (it is the source of truth and what a network channel loads to send).
- **Network channels are asynchronous.** Email and future channels start `pending`; a **separate periodic worker step drains them** — send (the plugin does its own short retry/backoff), then `delivered`/`failed`. This keeps a slow/failing SMTP from blocking the (single-threaded) worker or the scrape. Best-effort: a `failed` row is not re-drained — the next digest carries the new state. If the user has no active channel at all, a single `skipped_no_notifier` row is written.
- **Two-level config, no routing.** Each channel has an **admin** config (shared infrastructure) and a **user** config (personal target + on/off); the digest goes to *all* active channels, with no per-event routing. A channel is unavailable until the admin config is complete; the admin kill-switch can disable a whole channel for everyone, personal settings preserved.
- **Per-channel outcome.** Each delivery records its own result (`delivered`/`failed` with reason/`skipped`) — a broken channel never hides the others, and the outcomes are visible in the alert detail.

## What remains: the alert history

- In-app browsable list of all digests, with **read/unread** state (opening a notification marks it read; an unread badge on the dashboard is kept live by polling).
- A detail view showing the full digest.
- **Multi-select delete** of history entries.

## Further reading

- Detailed behaviour: [3-features/user/alerts-and-notifications.md](../3-features/user/alerts-and-notifications.md)
- Diff algorithm and pseudocode: [alert-engine](../4-capabilities/core/alert-engine.md)
- Payload contract: [alert-event](../4-capabilities/contracts/alert-event.md)
