# Phase 2 — Plugin system

> Feature-level recap. **In progress** — this file grows as the phase-2 MVPs land.

## What's implemented

_Phase 2 has just started; nothing user-facing yet. Items will appear here as they ship._

## Good to know

- Carries over from phase 1: `admin` is the default initial user (from `.env`), forced password change on first login, dark/light theme, version shown on the login page and in the sidebar.

## Useful Commands

Dev stack (builds from sources, reads `.env`):

```bash
cp .env.example .env                                    # once
docker compose -f compose-dev.yml up -d --build         # db + web + worker
docker compose -f compose-dev.yml --profile dev up -d   # + Adminer on :8081
docker compose -f compose-dev.yml down -v               # stop + reset the DB
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
