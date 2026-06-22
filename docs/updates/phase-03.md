# Phase 3 — Catalog & first scrape

> Feature-level recap. **In progress** — this file grows as the phase-3 MVPs land. User management came first (0.3.0, pulled forward from phase 10 so a standard `user` account can exist before the catalog); the catalog, the Dragon Store scraper and the Product Picker followed, with **real** scraping replacing the initial mock in 0.3.3.

## What's implemented

### 1) User management (MVP) — 0.3.0

So that a standard `user` account can exist (and be used to test the catalog and the rest of the phase), the admin can now create and list users.

- **Roles don't overlap.** An admin **governs** (creates accounts; later: scrapers, settings) and has **no** personal catalog/cart/notifications. Whoever wants to monitor prices uses a separate `user` account. There is **no self-registration**.
- **Admin → Users page** (`/admin/users`): a create form (username, first/last name, role, temporary password) + a list (username, name, role, status, last login). The new account must change its temporary password at first login.
- **The shell splits by role:** an admin lands in the admin area and never sees the user dashboard / SCRAPERS group; a standard user sees the user area. Profile and Log out are common.

### 2) Catalog, Dragon Store scraper & Product Picker — 0.3.1 → 0.3.3

- **Watch a Dragon Store product** by pasting its URL on the scraper's page; **preview** a scrape without saving (dry-run), or **Scrape now** to pull your watched products into the catalog. Scrape now is rate-limited per scraper by a cooldown. Adding a URL you already watch is rejected with a clear message.
- **Watched products** show like the preview — image, title (link), brand, category and a tags column, with a Remove button — and the title appears **as soon as you add it** (a one-off scrape resolves it).
- **Catalog page:** your products in a searchable, sortable, paginated table; each row shows photo (which enlarges on hover), title, **brand**, **category** breadcrumb and **tags**, with sorting by source, list price and availability too. Photo and title link to the shop; the source links to its scraper page. It fills in on its own right after a scrape.
- **Real scraping (0.3.3):** the scraper reads the live product page — real title, prices, availability, image, **brand** and **category** breadcrumb. Marketing/edition labels (e.g. _Edizione Limitata_, _Offerta Raven Prime_) are stripped from the title and shown as **tags**; pre-order items are tagged _Pre Order_ and count as orderable, while out-of-stock items are marked unavailable. Each scraper also shows its icon.

_Under the hood:_ the `Product` contract + per-user catalog tables (`products` / append-only `price_history`) with the Catalog Update Service as the single write path (delta, history, delisting). A polite, counted, retrying stdlib `context.http` client; the Dragon Store parser reads the page's JSON-LD `Product` (and `BreadcrumbList` for the category), taking the list price from the detail table (decoding windows-1252 + HTML entities) and ignoring the page's many related products. `brand` (text + optional link), `product_properties` (tags) and `category` (a breadcrumb of `{text, link}`) are generic `Product` fields the core just persists; the base scraper supplies the `add_property`/`add_child` mechanisms. The title sanitizer is Dragon-Store-specific; the watched list is backed by a product snapshot on the watch; plugin icons are auto-detected at load (`plugin-icon.ico` → `.svg`).

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
