# Frontend — Auth Manager

> **Layer 4 — Capability** · Audience: developer.
>
> English translation of the Italian reference [`docs-ita/4-capabilities/frontend/auth-manager.md`](../../../docs-ita/4-capabilities/frontend/auth-manager.md), limited to what is implemented (DOC-12). Delivered in phase 1 (`src/frontend/src/lib/auth/`).

## Purpose

The only frontend module that knows about tokens: cache, automatic header, refresh with retry, logout. UI and domain code never see a token (FE-4).

## Requirements

- **FAUTH-R1** — Holds `access_token` and `refresh_token`. Declared choice (hobby posture): access in memory, refresh in `localStorage` to survive a reload. The XSS risk is accepted: app behind login, no third-party content rendered.
- **FAUTH-R2** — Adds `Authorization: Bearer <access>` to every request from the API client.
- **FAUTH-R3** — On `401`: try the refresh and **retry the original request once**. Failed refresh → clear tokens + the guard redirects to login.
- **FAUTH-R4** — **Single-flight refresh**: one refresh in flight at a time; concurrent 401s await its result and reuse the new pair. Essential with rotation: concurrent refreshes would spend already-invalidated jtis and cause spurious logouts.
- **FAUTH-R5** — **Proactive refresh** when `expires_at` is near (< 60 s), to avoid the 401 round-trip on the happy path.
- **FAUTH-R6** — The forced-change flow is driven by `GET /api/me` (which is exempt from the gate and returns `must_change_password`); the route guard sends the user to the forced-change page.

## Shape

```
let refreshing: Promise<boolean> | null = null

async function apiFetch(path, init):
    if access near expiry: await refreshOnce()       # FAUTH-R5
    res = await fetch(path, withBearer(init))
    if res.status != 401: return res
    ok = await refreshOnce()                          # FAUTH-R4 (single-flight)
    if not ok: return res
    return await fetch(path, withBearer(init))        # one retry (FAUTH-R3)

function refreshOnce():
    if not refreshing:
        refreshing = doRefresh().finally(() => refreshing = null)
    return refreshing
```

`doRefresh()` posts the stored refresh token to `/api/auth/refresh`, stores the rotated pair on success, and clears the tokens on failure. The auth store's boot/sign-in actions then read `GET /api/me` to populate the user and let the guard route.
