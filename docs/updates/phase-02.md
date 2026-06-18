# Phase 2 — Plugin system

> Feature-level recap. **In progress** — this file grows as the phase-2 MVPs land.

## What's implemented

The **plugin system backbone**: plugins are self-contained folders that the app discovers on its own.

- Drop a folder under `src/plugins/scrapers/<name>/` or `src/plugins/notifiers/<name>/` with a `manifest.json` and a backend/frontend, **rebuild**, and the plugin appears by itself — no core code touched.
- A **scraper** shows up in the **SCRAPERS** group at the bottom of the sidebar (icon + name) with its own page; its API route is live under `/api/plugins/<route>` and visible in Swagger (`/api/docs`).
- A **notifier** loads and is listed by `GET /api/plugins`, but never appears in the sidebar (its UI arrives in later phases).
- Set `"enabled": false` in a manifest and rebuild → the plugin disappears everywhere (sidebar, API, bundle). A broken plugin is rejected on its own: it is logged and skipped, the app and the other plugins keep running.
- Shipped for this phase: **TP Scraper** (a page with a button that pings its own backend route) and **TP Notifier** (backend-only). They are throwaway test plugins — they don't scrape or send — and will be removed when real plugins land.

## API & Swagger

The HTTP API is documented interactively at **<http://localhost:8080/api/docs>** (Swagger UI — ReDoc at `/api/redoc`, raw schema at `/api/openapi.json`). Every endpoint carries a one-line summary of what it does.

- **Everything is behind authentication**, except (by necessity) `GET /api/health`, `POST /api/auth/login` and `/api/auth/refresh`, and the plugin icon (`/api/plugin-assets/...`, loaded by the browser as an `<img>`, which cannot carry the bearer token).
- **Authorize in Swagger:** call `POST /api/auth/login` (`admin` + your password) to get an `access_token`, then click **🔓 Authorize** (top-right), paste **just the token** (no `Bearer ` prefix), *Authorize* → *Close*. Every "Try it out" then carries it automatically.
- The access token lasts ~15 minutes; when it expires you get `401` — log in again or call `POST /api/auth/refresh` with your refresh token.
- Plugin routes appear under the **`Plugin: <name>`** tag (e.g. the TP Scraper's `GET /api/plugins/tp-scraper/ping`); the version link in the sidebar opens this page in a new tab.

## Good to know

- Carries over from phase 1: `admin` is the default initial user (from `.env`), forced password change on first login, dark/light theme, version shown on the login page and in the sidebar.
- **Activation is static.** A plugin's `enabled` flag and its presence in the UI are baked at build time, so enabling/disabling a plugin or adding one needs a **rebuild + restart** (`docker compose -f compose-dev.yml up -d --build`), not just a restart.
- The frontend plugin registry (`src/frontend/src/generated/`) is **generated** from the manifests and gitignored; the dev/build/check scripts regenerate it automatically (`build:plugins` runs on `predev`/`prebuild`/`precheck`), so a fresh checkout has it after the first `npm run dev`/`build`/`check`.
- Phase-2 stubs (declared): a plugin's `logger` writes to stdout (the `system_log` table lands ~phase 10) and its admin `config` is empty (the ConfigField infra lands in phases 7/9/10).

## Useful Commands

Dev stack (builds from sources, reads `.env`):

```bash
cp .env.example .env                                    # once
docker compose -f compose-dev.yml up -d --build         # db + web + worker
docker compose -f compose-dev.yml --profile dev up -d   # + Adminer on :8081
docker compose -f compose-dev.yml down -v               # stop + reset the DB
```

Regenerate the frontend plugin registry by hand (normally automatic on dev/build/check):

```bash
cd src/frontend && npm run build:plugins                # writes src/generated/plugin-registry.ts
```

**Force the UI language to Italian** (V1 is English-only, no selector). In the browser DevTools **Console**, run, then reload (F5):

```js
localStorage.setItem('wea_lang', 'it'); // switch to Italian
// localStorage.setItem('wea_lang', 'en'); // back to English
// localStorage.removeItem('wea_lang');    // back to the default (English)
```

Headless check of the language (from a Windows shell, Chrome installed):

```bash
"/c/Program Files/Google/Chrome/Application/chrome.exe" \
  --headless=new --disable-gpu --dump-dom --virtual-time-budget=9000 \
  http://localhost:8080/login
```
