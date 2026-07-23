# Phase 7 — Email notifications 🎉

> Feature-level recap. Phase 7 adds the **first real delivery channel**: the alert digests that
> phase 6 wrote to the in-app history now also **leave the app and arrive by email**. The admin
> configures the SMTP server once; each user adds their own address in the Profile, presses **Test**
> to prove it, and from then on — whenever a scrape produces events — the **digest lands in their
> inbox**, formatted and readable. This closes the product's minimum value chain: at the end of this
> phase Watch 'Em All does its whole job end to end (the **0.1**).
>
> 🚧 **In progress (0.7.x).** This page fills in as the phase's MVPs ship; the list below tracks what
> has actually landed.

## What's implemented (0.7.0)

### 1) The notifier contract + channel dispatch

A notifier is now a real plugin family: it declares its config (a list of `ConfigField`) and implements
`send` / `send_test`. When the alert engine writes a digest, the core records **one delivery per active
channel** and hands the payload to each notifier — the core decides *what* and *when*, the plugin decides
*how to format* and *where to send*. When a user has no active channel, the notification is still recorded
in the Alert History (it's the source of truth) and marked `skipped_no_notifier`.

### 2) The in-app channel is now one of the channels

The in-app history you've had since phase 6 is now modelled as a first-class channel (`in_app`), shown in
the Profile channel list alongside email. It is **always on for the user** (you can't switch it off) and
its "delivery" is local — the record itself — so it's marked delivered instantly, never queued. Only an
**admin** can switch it off globally (for a particular need); while off, the inbox is hidden for everyone.

### 3) Two-level configuration with dynamic forms

Every channel has an **admin** config (shared infrastructure — for email: SMTP host, port, credentials,
sender) and a **user** config (personal target — the address). The core renders one dynamic form from the
declared schema for both. Saved keys are filtered to the declaring side (a user can't inject an admin key);
**secrets are write-only** — stored but never returned, only an `is_set` indicator. A channel is "available"
to users only once the admin config is complete.

### 4) Email channel — SMTP, HTML digest + text fallback, retries

The Email notifier sends over SMTP with STARTTLS (standard library only). The digest renders as HTML
(inline CSS for client compatibility) with a plain-text fallback: per-cart sections with the event badges,
old → new price, **provenance**, links, totals and threshold. Transient errors are retried a few times with
backoff; a permanent failure (recipient refused / auth) fails immediately with a readable reason.

### 5) The Profile channels UI, the admin notifier page, and delivery outcomes

The **Profile → Notification channels** section lists each channel with its composite status, the personal
form, an on/off toggle and a **Test** button (outcomes shown as a toast). The **Admin → Notifiers** page
carries the system config form, the global **kill-switch** and a channel test. Opening a notification shows
its **per-channel delivery outcomes** (delivered / pending / failed with reason / skipped). A dashboard
banner nudges a user with no external channel active to set one up — never alarming, since in-app is always on.

_Under the hood:_ delivery is decoupled from the scrape (see the design note below). New tables:
`alert_delivery`, `notifier_admin_config`, `notifier_user_config`. The `NotifierPlugin` contract, the
`ConfigField` model, the dynamic form, and a single top-center toast portal are the shared pieces the next
notifiers (Discord, Teams, …) will reuse. A **Debug** sidebar entry (dev-only, to be removed before v1)
links to Mailpit, Swagger and the DB browser.

## Design note — delivery is **asynchronous**

Decided while reasoning through phase 6 (2026-07-22): computing/writing the digest (cheap — `alert_log`
is already the durable part) is kept **separate** from delivering it to channels (slow, can fail). When a
digest is written, one **`alert_delivery` row per active channel** is created in state **`pending`**; a
**separate worker step drains them** (send + retry/backoff, then `delivered` / `failed`). This keeps a
single scrape run from blocking the (single-threaded, serial) worker on SMTP, and stays best-effort — the
in-app history is the source of truth, a failed send is not retried forever, and the next digest carries
the current state. So phase-7 delivery is **not** sent inline inside the alert run.

## Good to know

- **In-app history stays the source of truth.** A notification is always recorded in the Alert
  History even if no channel is configured or a send fails; email is an additional delivery, not a
  replacement.
- **Two-level config.** The admin sets the shared SMTP server (host / port / credentials); each user
  supplies their own address and enables the channel for themselves. Without the admin config the
  channel shows as "not available" to users.
- **Secrets are write-only.** Secret config fields (e.g. SMTP password) are masked and never shown
  back — only an `is_set` indicator.

## Useful Commands

```bash
docker compose -f compose-dev.yml up -d --build         # db + web + worker + pgweb (DB browser on :8081)
docker compose -f compose-dev.yml down -v               # reset the DB (admin recreated from .env)
```

**pgweb** (DB browser) — http://localhost:8081. New table to inspect this phase: `alert_delivery`.
