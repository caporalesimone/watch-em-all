# User management (admin)

> **Layer 3 — Admin feature** · Audience: architects, developers.
>
> English translation of the Italian reference [`docs-ita/3-features/admin/user-management.md`](../../../docs-ita/3-features/admin/user-management.md), limited to what is implemented (DOC-12). This MVP — **create + list accounts** + a role-split shell — is **phase 3's first step (0.3.0)**, pulled forward from phase 10 so a standard `user` account can exist before the catalog itself. The richer lifecycle (reset, disable, deferred delete, filters, notifications) stays in phase 10.

## Roles don't overlap

Two roles, one per account (`admin` | `user`), with separate, non-overlapping duties ([personas-and-roles](../../1-business/personas-and-roles.md)):

- the **admin governs the system** (creates accounts, later: scrapers, settings) and **does not own** a personal catalog/cart/notifications;
- the **user owns their data** (catalog, carts, alerts).

Whoever administers *and* wants to monitor prices uses **two accounts** — one `admin`, one `user`. There is **no self-registration**: accounts exist only because an admin created them (USR-R1).

## What's implemented

- **Create an account** (USR-R1/R2/R15): the admin sets the **email address** that is also the username (10.B23 — validated and stored lowercase), **first and last name** (both required) and the role. There is **no password field** (10.B24): the server generates one and mails it directly over SMTP, never through the notification pipeline, so it is never written to `alert_log` and never readable in the in-app history. The account is created with `must_change_password`, so the person chooses their own at first sign-in. Duplicate username is refused; so is creation while the email channel is off or unconfigured (422 `email_channel_unavailable`) — an account whose password nobody can read is not usable.
- **List accounts**: username, name, role, status (active / disabled / change-pending), last login.
- **Role-split shell**: an admin lands in the admin area (the Users page) and never sees the user dashboard or the SCRAPERS group; a standard user sees the user area. Profile and Log out are shared; the route guard keeps each role in its lane.

## Endpoints

| Method | Path | Role | Body | Notes |
|---|---|---|---|---|
| POST | `/api/admin/users` | 🛡 | `{username, first_name, last_name, role}` | generates the password and mails it, then creates with a forced first-login change; duplicate username → 409; email channel unusable → 422 |
| GET | `/api/admin/users` | 🛡 | — | lists all accounts |

## Deferred to phase 10

Reset password, disable/enable, deferred soft-delete (grace period + restore), status filters, last-login sorting, courtesy notifications on disable/deletion, and the per-user load dashboard.
