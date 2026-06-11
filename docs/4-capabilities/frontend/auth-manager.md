# Frontend — Auth Manager

> **Layer 4 — Capability** · Audience: developer · Pseudocodice ammesso. Backend: [auth](../core/auth.md).

## Scopo

Unico modulo del frontend che conosce i token: cache, header automatico, refresh con retry, logout. UI e domain layer non vedono mai un token.

## Requisiti

- **FAUTH-R1** — Conserva `access_token` e `refresh_token`. Scelta dichiarata (postura hobby): access in memoria, refresh in `localStorage` per sopravvivere al reload. Il rischio XSS è accettato: app dietro login, nessun contenuto di terzi renderizzato.
- **FAUTH-R2** — Aggiunge `Authorization: Bearer <access>` a ogni richiesta del client API.
- **FAUTH-R3** — Su `401`: tenta il refresh e **riesegue una sola volta** la richiesta originale. Refresh fallito → pulizia token + redirect al login.
- **FAUTH-R4** — **Single-flight sul refresh**: un solo refresh in volo; le richieste concorrenti in 401 attendono il suo esito e riusano la nuova coppia. Indispensabile con la rotazione: refresh concorrenti spenderebbero jti già invalidati causando logout spuri.
- **FAUTH-R5** — Refresh **proattivo** quando `expires_at` è vicino (es. < 60 s), per evitare il giro 401 sul percorso felice.
- **FAUTH-R6** — Gestisce il flusso `must_change_password` (403 dedicato → route di cambio password forzato).

## Pseudocodice

```
let refreshing: Promise<void> | null = null

async function apiFetch(req):
    attachBearer(req, access)
    res = await fetch(req)
    if res.status != 401: return res
    await refreshOnce()                      # FAUTH-R4
    attachBearer(req, access)
    return await fetch(req)                  # un solo retry (FAUTH-R3)

async function refreshOnce():
    if refreshing: return refreshing         # single-flight
    refreshing = (async () => {
        try:
            r = await POST("/api/auth/refresh", {refresh_token})
            store(r.access_token, r.refresh_token, r.expires_at)   # coppia RUOTATA
        catch:
            clearTokens(); redirect("/login")
        finally:
            refreshing = null
    })()
    return refreshing
```

## Flusso

```
richiesta A ─┐
richiesta B ─┼─ 401 → [single-flight] un solo refresh → nuova coppia → retry A, B, C
richiesta C ─┘                  └─ fallito → logout + redirect login
```
