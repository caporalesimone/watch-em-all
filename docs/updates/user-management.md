# User management (MVP)

> Feature-level recap. A small slice pulled forward from phase 10, before the catalog phase (0.3.0).

## What's implemented

So that a standard `user` account can exist (and be used to test the coming features), the admin can now create and list users.

- **Roles don't overlap.** An admin **governs** (creates accounts; later: scrapers, settings) and has **no** personal catalog/cart/notifications. Whoever wants to monitor prices uses a separate `user` account. There is **no self-registration**.
- **Admin → Users page** (`/admin/users`): a create form (username, first/last name, role, temporary password) + a list (username, name, role, status, last login). The new account must change its temporary password at first login.
- **The shell splits by role:** an admin lands in the admin area and never sees the user dashboard / SCRAPERS group; a standard user sees the user area. Profile and Log out are common.

## Good to know

- To try it: log in as `admin` → **Users** → create a `user` (pick a temporary password) → log out → log in as that user (it will force a password change), and from there test the user-facing features.
- Deferred to phase 10: reset password, disable/enable, deferred delete (grace + restore), status filters, last-login sort, courtesy notifications, the load dashboard.

## Useful Commands

```bash
docker compose -f compose-dev.yml up -d --build         # rebuild + restart
docker compose -f compose-dev.yml down -v               # reset the DB (admin recreated from .env, must change password)
```
