# Phase 1 — Foundations

> Feature-level recap of the live skeleton: real app, auth, the SPA shell.

## What's implemented

**Backend (FastAPI)**

- **Configuration & startup**: `config.yaml` + `.env` with `${VAR}` interpolation, validated at boot (fails fast on a missing value). The product **version** is baked into the image from the git tag and read at startup.
- **Health**: `GET /api/health` reports app liveness, DB reachability and the version (503 if the DB is down). Swagger at `/api/docs`.
- **Users & initial admin**: a `users` table; on first boot an admin is created from `.env` with a forced password change. Every user has a **first and last name**.
- **Authentication (JWT)**: login / logout; refresh tokens with **rotation** and **reuse detection** (a reused refresh logs you out everywhere); login **rate limiting**; disabled accounts get a dedicated message.
- **Password change**: the **forced first change** (right after the first login) does **not** ask for the current password; the **normal change** (from Profile) always does.
- **Profile**: `GET/PATCH /api/me` returns id, username, first/last name, role, locale.

**Frontend (SvelteKit SPA)**

- **Shell**: persistent sidebar (Dashboard · Profile · Log out) + header with a **dark/light theme toggle** (no flash on load). Everything is internationalised (English now, Italian dictionary present).
- **Login → forced change → shell** flow, driven by a route guard.
- **Forced-change page**: only *new* + *confirm* (no current password), greets you by name; a hidden username field helps password managers.
- **Dashboard**: greets by first name ("Welcome, &lt;name&gt;").
- **Profile**: shows Username / Name / Surname / Role; lets you change the password (current password required).
- The built SPA is served by the same `web` container that serves the API.

## Good to know

- **Credentials (fresh DB)**: `admin` / `admin12345` → you are forced to set a new password, then sign in again with it. (Set your own in `.env` via `ADMIN_INITIAL_USERNAME` / `ADMIN_INITIAL_PASSWORD`.)
- A password change is a **global logout** (by design): after changing it you are sent back to login.
- The **worker is still a stub** in this phase, so `/api/health` shows `worker_heartbeat_age_s: null` — expected (the real worker arrives in phase 4).
- After rebuilding the frontend, **hard-refresh** the browser (Ctrl+Shift+R): bundles are content-hashed and the old one may be cached.
- Adding the name columns changed the DB schema; on an existing dev DB do a **`docker compose down -v`** so the fresh schema is created.
- Chrome's "Issues" panel may show two **viewport** warnings (`maximum-scale` / `user-scalable`) — those come from a **browser extension**, not the app; untick "Include third-party issues" or test in incognito.
- **Preview the Italian translation**: V1 is English-only (no language selector), but the `it` dictionary ships. In the browser console run `localStorage.setItem('wea_lang','it')` and reload to see the UI in Italian; `localStorage.removeItem('wea_lang')` (or set it to `'en'`) and reload to go back.
- What works: login, forced change, normal change, profile, theme, health, Swagger. What's not here yet: catalog, carts, alerts, admin pages (later phases).

## Useful Commands

Docker runs inside **WSL** (Ubuntu); the repo is at `/mnt/d/#Simone/watch-em-all`. Run these from a WSL shell in the repo (or wrap with `wsl.exe -d Ubuntu-24.04 -e bash -lc "cd '/mnt/d/#Simone/watch-em-all' && <cmd>"`).

```bash
# fresh start (rebuild images + clean database)
docker compose down -v
docker compose up -d --build

# rebuild just the app after a code change
docker compose up -d --build web worker

# logs / status
docker compose ps
docker compose logs -f web

# health (version + db)
curl -s http://localhost:8080/api/health

# quick auth probe (login → token)
curl -s -X POST http://localhost:8080/api/auth/login \
  -H 'content-type: application/json' -d '{"username":"admin","password":"admin12345"}'

# backup / restore (ops image; -T avoids stdin capture when scripted)
docker compose run --rm -T ops backup.sh
docker compose stop web worker
docker compose run --rm -T -e RESTORE_ASSUME_YES=1 ops restore.sh /backups/watchemall-backup-<date>.tar.gz
docker compose up -d web worker
```

Headless browser checks (run from a **Windows** shell — Chrome is installed there; WSL forwards `localhost`):

```bash
# render a page after JS runs and dump the DOM (quick visual check)
"/c/Program Files/Google/Chrome/Application/chrome.exe" \
  --headless=new --disable-gpu --dump-dom --virtual-time-budget=9000 \
  http://localhost:8080/login

# drive a full flow with Puppeteer (puppeteer-core + the installed Chrome)
#   npm i puppeteer-core   then point executablePath at chrome.exe
node drive.js
```
