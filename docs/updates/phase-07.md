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

_Nothing merged yet — entries land here as each MVP ships._

<!--
As MVPs land, document them here in the same user-facing voice as the earlier phases, e.g.:

### 1) The notifier contract + channel dispatch
### 2) Two-level configuration (admin system config + per-user config)
### 3) Email channel — SMTP send, HTML digest + text fallback, retries
### 4) The Profile channels UI + the admin notifier page
### 5) Delivery outcomes visible in the alert history

_Under the hood:_ …
-->

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
