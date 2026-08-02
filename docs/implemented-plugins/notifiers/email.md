# Email — Notifier

> **Implemented plugin** · Type: notifier · English mirror of the Italian reference
> [`docs-ita/implemented-plugins/notifiers/email.md`](../../../docs-ita/implemented-plugins/notifiers/email.md).
> Generic contract: [notifier-plugin](../../3-features/plugins/notifier-plugin.md).

## What it does

Delivers alert digests by **email (SMTP)**. It is the reference channel: works with any mailbox, no
third-party account needed. Standard library only (`smtplib` + `email`), no external dependencies.

## Configuration

| Level | Fields | Notes |
|---|---|---|
| **Admin** (system) | `smtp_host`, `smtp_port` (default 587), `smtp_user`, `smtp_password` (secret), `use_tls` (default true), `from_address` | Set on the Admin → Notifiers page; until complete the channel is "not available" |
| **User** | nothing but the on/off flag | In the Profile. Since 10.B25 the channel declares **no user fields**: the recipient is the account's own address (`contact_email`, or the username, which since 10.B23 *is* an address), injected by the core as `account_email`. One place where a person is reached, so there is no second field to disagree with the first. The channel arrives switched on for a new account. |

## Formatting

- **Digest** (`alert_digest`): a concise subject; an HTML body with one section per cart — event
  badges, a product table with provenance (the source plugin id), before → after price, the
  **Difference** and a link; totals and threshold. A `text/plain` fallback is always included.
- **Difference** is the signed percentage change between the two prices in the row — positive when
  the price went up, negative when it came down, coloured accordingly, an em dash when there is no
  earlier price to compare against. It is deliberately **not** the product's `discount_pct`, which is
  the sale discount against the list price: the column used to show that with a hardcoded minus sign,
  so a product that had left a sale and gone *up* was reported as `-0%` (issue
  [#37](https://github.com/caporalesimone/watch-em-all/issues/37)). One decimal is kept when it is not
  zero, so a real sub-1% move never renders as `0%`.
- Strings live behind i18n keys in the plugin's `backend/i18n/` (V1: `en.json` only). Currency is
  rendered as a symbol (default €).

## Errors and retries

SMTP unreachable / transient failures: a few attempts with backoff, then a readable
`NotifierDeliveryError` → `failed` outcome with the reason + an admin log warning. A permanently
refused recipient or an auth failure fails immediately (no retry).

## Dev testing

The dev compose ships **Mailpit** (SMTP on `1025`, inbox UI on `http://localhost:8025`). In dev,
configure the channel with `smtp_host=mailpit`, `smtp_port=1025`, TLS off. Production uses a real SMTP
server; Mailpit is never part of the release stack.

## Open points

| ID | Point |
|---|---|
| EML-Q1 | Product images: link-only (current default) vs embedded — kept link-only. |
| EML-Q2 | Per-cart product limit before truncation — no truncation yet; revisit on a real digest. |
