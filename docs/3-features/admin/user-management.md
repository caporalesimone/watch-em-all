# User management (admin)

> **Layer 3 — Admin feature** · Audience: architects, developers.
>
> English translation of the Italian reference [`docs-ita/3-features/admin/user-management.md`](../../../docs-ita/3-features/admin/user-management.md), limited to what is implemented (DOC-12). **Create + list accounts** landed as phase 3's first step (0.3.0), pulled forward so a standard `user` account could exist before the catalog itself; the rest of the lifecycle — reset, disable, deferred deletion with restore and purge, filters, notices — is phase 10.

## Roles don't overlap

Two roles, one per account (`admin` | `user`), with separate, non-overlapping duties ([personas-and-roles](../../1-business/personas-and-roles.md)):

- the **admin governs the system** (creates accounts, later: scrapers, settings) and **does not own** a personal catalog/cart/notifications;
- the **user owns their data** (catalog, carts, alerts).

Whoever administers *and* wants to monitor prices uses **two accounts** — one `admin`, one `user`. There is **no self-registration**: accounts exist only because an admin created them (USR-R1).

## What's implemented

- **Create an account** (USR-R1/R2/R15): the admin sets the **email address** that is also the username (10.B23 — validated and stored lowercase), **first and last name** (both required) and the role. There is **no password field** (10.B24): the server generates one and mails it directly over SMTP, never through the notification pipeline, so it is never written to `alert_log` and never readable in the in-app history. The account is created with `must_change_password`, so the person chooses their own at first sign-in. Duplicate username is refused; so is creation while the email channel is off or unconfigured (422 `email_channel_unavailable`) — an account whose password nobody can read is not usable.
- **List accounts**: username, name, role, status (active / disabled / change-pending / being deleted), last login. Filterable by status and sortable by last sign-in, with never-signed-in at the dormant end (USR-R13/R14).
- **Reset a password** (USR-R3): the only way an admin changes somebody's password. A new one is generated, mailed and forced to be changed; every open session ends (AUTH-R5). The admin never sees it.
- **Disable and re-enable** (USR-R4) — but **never your own account** (10.B1): with a single administrator that is a lockout with no way back through the application.
- **Deferred deletion** (USR-R7/R8): deleting marks the account and sets a deadline instead of destroying anything. The person is locked out immediately; until the deadline an admin can cancel, and the account comes back **disabled**, never directly active.
- **Deleting for good** — the worker's nightly sweep at the deadline (USR-R9), or *delete permanently* on an account already marked (USR-R9b, 10.B27). Both run the same code: every plugin drops its rows first, and the core cascade only follows **if all of them succeed** — half a deletion is the one state nothing can recover from. A plugin that refuses leaves the account marked, with the reason in the system log.
- **Role-split shell**: an admin lands in the admin area (the Users page) and never sees the user dashboard or the SCRAPERS group; a standard user sees the user area. Profile and Log out are shared; the route guard keeps each role in its lane.

## What the person is told

Three things that happen *to* an account are announced to its owner (USR-R11): **disabled**, **scheduled for deletion** — naming the date it will happen — and **deleted**. The wording comes from the system-message catalog and can be rewritten by the admin.

These notices **ignore the recipient's email preference** (10.B26). That switch governs notifications, the things somebody asked to be told about; none of these is one. There is also a practical half: the in-app copy of *"your account has been disabled"* can only be read by signing in, which is exactly what the message says has stopped being possible. So each notice is written to the in-app history **and** mailed directly — email is taken out of the ordinary delivery pass precisely so the two are not two copies of the same mail.

The deletion notice is the exception with no in-app half, for the obvious reason: it is sent **after** the delete has committed, when there is no history left to write to. Announcing it earlier could be a lie, since a plugin may still refuse and the account survive.

## Endpoints

| Method | Path | Role | Body | Notes |
|---|---|---|---|---|
| POST | `/api/admin/users` | 🛡 | `{username, first_name, last_name, role}` | generates the password and mails it, then creates with a forced first-login change; duplicate username → 409; email channel unusable → 422 |
| GET | `/api/admin/users` | 🛡 | — | lists all accounts; `?status=`, `?sort=`, `?order=` |
| PATCH | `/api/admin/users/{id}` | 🛡 | `{is_active}` | enable/disable; never your own → 403 |
| POST | `/api/admin/users/{id}/reset-password` | 🛡 | — | new password generated, mailed, change forced, sessions ended |
| DELETE | `/api/admin/users/{id}` | 🛡 | — | mark for deletion with a deadline; nothing is destroyed |
| POST | `/api/admin/users/{id}/restore` | 🛡 | — | cancel a pending deletion → the account is disabled |
| DELETE | `/api/admin/users/{id}/purge` | 🛡 | — | destroy an already-marked account now → 204; not marked → 409; a plugin refused → 500 and nothing removed |
