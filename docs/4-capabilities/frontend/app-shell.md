# Frontend — App shell and pages

> **Layer 4 — Capability** · Audience: developer.
>
> English translation of the Italian reference [`docs-ita/4-capabilities/frontend/app-shell.md`](../../../docs-ita/4-capabilities/frontend/app-shell.md), limited to what is implemented (DOC-12). Phase 1 ships the SPA scaffold, theme, i18n, the Auth Manager, the protected shell and the login / forced-change / profile pages. The feature pages (catalog, carts, history, alerts, admin) arrive in later phases.

## Stack

**SvelteKit 2** (Svelte 5, runes) in **SPA** mode (CSR, `adapter-static` with an `index.html` fallback; no SSR), TypeScript strict, **Tailwind CSS 4** (class-based dark mode), Svelte stores for shared state, Fetch via the Auth Manager, **svelte-i18n** (runtime dictionaries, fallback `en`). Node 22 LTS. See [auth-manager](auth-manager.md).

## Structure (phase 1)

```
src/frontend/src/
├── routes/            # +layout (shell + guard), +page (dashboard),
│                      # login/, change-password/, profile/
├── lib/
│   ├── components/    # Sidebar, Header (shared design system)
│   ├── stores/        # auth, theme
│   ├── api/           # typed client (uses lib/auth)
│   └── auth/          # Auth Manager
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

- **Left sidebar** (persistent): Dashboard · Profile · Log out. Feature entries (catalog, carts, scrapers…) join in later phases.
- **Header**: theme toggle (the language selector is planned but not exposed in V1, English-only).

## Theme and language

- Light/dark theme, **dark by default**; per-browser preference in `localStorage`, applied **before first paint** (no flash, FE-9), via a `.dark` class on `<html>`.
- Language is per-account (`users.locale`); **V1 is English-only** (`locale` fixed to `en`, selector hidden), but the whole machinery (keys, language files, fallback) is in place.

## Implemented pages (phase 1)

| Page | Responsibility |
|---|---|
| Dashboard | greets by **first name** ("Welcome, &lt;name&gt;"); placeholder until catalog/carts arrive |
| Login | username + password; surfaces auth error codes |
| Forced change | new + confirm only (no current password); greets by name |
| Profile | **account fields** (Username, Name, Surname, Role — read-only), change password (current password required), language (read-only, English) |
