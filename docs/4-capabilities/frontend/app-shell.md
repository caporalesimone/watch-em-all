# Frontend — App shell and pages

> **Layer 4 — Capability** · Audience: developer.
>
> English translation of the Italian reference [`docs-ita/4-capabilities/frontend/app-shell.md`](../../../docs-ita/4-capabilities/frontend/app-shell.md), limited to what is implemented (DOC-12). Phase 1 ships the SPA scaffold, theme, i18n, the Auth Manager, the protected shell and the login / forced-change / profile pages; phase 2 the dynamic plugin pages; phase 3 the **Product Picker** (catalog) page; phase 5 the **Carts** pages; the admin area (users, scrapers + schedule, notifiers, settings, system logs) ships across phases 4–5. The **Price history** charts and the **Alerts** inbox pages arrive in later phases and stay in the Italian reference.

## Stack

**SvelteKit 2** (Svelte 5, runes) in **SPA** mode (CSR, `adapter-static` with an `index.html` fallback; no SSR), TypeScript strict, **Tailwind CSS 4** (class-based dark mode), Svelte stores for shared state, Fetch via the Auth Manager, **svelte-i18n** (runtime dictionaries, fallback `en`). Node 22 LTS. See [auth-manager](auth-manager.md).

## Structure

```
src/frontend/src/
├── routes/            # +layout (shell + guard), +page (dashboard),
│                      # login/, change-password/, profile/,
│                      # catalog/ (Product Picker), carts/ + carts/[id],
│                      # admin/ (logs, users, scrapers + scrapers/[id] + schedule,
│                      #         notifiers, settings, feature-flags),
│                      # plugins/[...rest] (dynamic plugin pages)
├── lib/
│   ├── components/    # shared design system (also for plugins: $lib/components)
│   ├── stores/        # auth, theme, plugins
│   ├── api/           # typed clients per endpoint (use lib/auth)
│   └── auth/          # Auth Manager
├── generated/         # plugin-registry.ts (GENERATED, never by hand)
└── i18n/              # en.json (complete fallback) + it.json
```

## Boot sequence

```
boot SPA → apply theme from localStorage before first paint (no flash)
        → init i18n (locale set at module load)
        → restore session: refresh token? → GET /api/me
        → must_change_password? → forced change page
        → else → shell (sidebar + content)
        → no session → login
```

The **forced password change** page shows only *new password* + *confirm*: the current password is **not** asked (the prompt appears right after the first login, so it would be redundant); the change from Profile always asks for it. `GET /api/me` is **exempt** from the `must_change_password` gate so the boot can read the name and the flag and route correctly. Both change-password forms include a hidden `username` field (`autocomplete="username"`) so password managers associate the new credentials.

## Shell and navigation

- **Left sidebar** (persistent): Dashboard · **Product Picker** · **Carts** · **Alerts** (with a live **unread badge**) · Profile · Log out, plus a collapsible **SCRAPERS** group at the bottom (populated dynamically from `GET /api/plugins` — phase 2, see [Plugins](#plugins-phase-2)), kept **last** so it grows without shifting the core entries. The Price history entry joins when that page arrives.
- **No top bar**: the **theme** (light/dark) toggle lives in **Profile → Settings** (the language selector is planned but not exposed in V1, English-only).

## Theme and language

- Light/dark theme, **dark by default**; per-browser preference in `localStorage`, applied **before first paint** (no flash, FE-9), via a `.dark` class on `<html>`.
- Language is per-account (`users.locale`); **V1 is English-only** (`locale` fixed to `en`, selector hidden), but the whole machinery (keys, language files, fallback) is in place.

## Implemented pages

| Page | Responsibility | Phase |
|---|---|---|
| Dashboard | greets by **first name** ("Welcome, &lt;name&gt;") | 1 |
| Login | username + password; surfaces auth error codes | 1 |
| Forced change | new + confirm only (no current password); greets by name | 1 |
| Profile | **account fields** (Username, Name, Surname, Role — read-only), a **Settings** section (light/dark theme toggle), change password (current password required), language (read-only, English) | 1 |
| Product Picker | server-side paginated **catalog** table (`GET /api/catalog`): name search, sort by column, filters by availability / delisted, provenance (plugin icon). Read-only view — the catalog is populated by a scrape | 3 |
| Carts | cart **cards** and a **detail** page: create (mode fixed at creation), rename, delete, add/remove members; the Cart Engine's computed totals (full / discounted), plugin adjustments (scraper_specific), final estimate, savings threshold state and the delisted-member health flag; the per-cart **alert types** are chosen on the detail page | 5 |
| Alerts | the in-app **alert history**: a paginated, mailbox-style list with an unread marker and **multi-select delete**, and a **detail** view of the digest (per-cart events + per-product tags/prices/provenance). Opening one marks it read; the sidebar's unread badge is kept live | 6 |

## Plugins (phase 2)

When the user is authed, the shell fetches `GET /api/plugins` and reconciles it against the build-time generated registry (`src/generated/plugin-registry.ts`):

- a `lib/stores/plugins` store holds the mountable scrapers; the **SCRAPERS** sidebar group renders them (icon + name → `route_base`). Notifiers never appear here.
- a single catch-all route `routes/plugins/[...rest]/+page.svelte` resolves `route_base` from the path and lazily mounts the plugin component, registering its i18n namespace through `$lib`.
- bundle/runtime mismatches are surfaced in the console (never a broken page).

See [plugin-discovery](plugin-discovery.md) for the full contract.

## Roles — the split shell (user-management MVP)

Roles don't overlap ([personas-and-roles](../../1-business/personas-and-roles.md)), so the shell branches on `me.role`:

- **admin** → the admin area. Sidebar (admin only): **System logs** (`/admin/logs`), **Users** (`/admin/users`), **Scrapers** (`/admin/scrapers`, child *Schedule*), **Notifiers** (`/admin/notifiers`), **Settings** (`/admin/settings`, child *Feature flags*). The admin never sees the user dashboard or the SCRAPERS group.
- **user** → the user area (dashboard + SCRAPERS, and the feature pages as they arrive).

Profile and Log out are common. The route guard sends an admin away from `/` to `/admin/users` and keeps a standard user out of `/admin/*`; plugin discovery loads only for users. See [user-management](../../3-features/admin/user-management.md).
