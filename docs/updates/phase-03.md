# Phase 3 — Catalog & first scrape

> Feature-level recap. **In progress** — this file grows as the phase-3 MVPs land. The **first MVP is user management** (0.3.0), pulled forward from phase 10 so a standard `user` account can exist before the catalog itself; the catalog, the Dragon Store scraper and the Product Picker follow.

## What's implemented

### 1) User management (MVP) — 0.3.0

So that a standard `user` account can exist (and be used to test the catalog and the rest of the phase), the admin can now create and list users.

- **Roles don't overlap.** An admin **governs** (creates accounts; later: scrapers, settings) and has **no** personal catalog/cart/notifications. Whoever wants to monitor prices uses a separate `user` account. There is **no self-registration**.
- **Admin → Users page** (`/admin/users`): a create form (username, first/last name, role, temporary password) + a list (username, name, role, status, last login). The new account must change its temporary password at first login.
- **The shell splits by role:** an admin lands in the admin area and never sees the user dashboard / SCRAPERS group; a standard user sees the user area. Profile and Log out are common.

## Good to know

- To try it: log in as `admin` → **Users** → create a `user` (pick a temporary password) → log out → log in as that user (it will force a password change), and from there test the user-facing features.
- Deferred to phase 10: reset password, disable/enable, deferred delete (grace + restore), status filters, last-login sort, courtesy notifications, the load dashboard.

## Useful Commands

```bash
docker compose -f compose-dev.yml up -d --build         # rebuild + restart — app on http://localhost:8080
docker compose -f compose-dev.yml --profile dev up -d   # also start Adminer (DB browser) on http://localhost:8081
docker compose -f compose-dev.yml down -v               # reset the DB (admin recreated from .env, must change password)
```

**Adminer** (DB browser) — once started with the `dev` profile, open **http://localhost:8081** and log in with:

| Field | Value |
|---|---|
| System | PostgreSQL |
| Server | `db` (the Compose service name, not `localhost`) |
| Username | `POSTGRES_USER` from `.env` |
| Password | `POSTGRES_PASSWORD` from `.env` |
| Database | `POSTGRES_DB` from `.env` |

> The `dev` profile must be passed every time you want Adminer; without it only `db`/`web`/`worker` start.
