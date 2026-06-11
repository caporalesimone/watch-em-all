# Fase 1 — Fondamenta

> Stato: ☐ da iniziare · Prerequisiti: nessuno · [Indice del flusso](README.md)

## Obiettivo

Lo scheletro vivo: stack su Docker, database, autenticazione, shell della SPA. Tutto ciò che le fasi successive danno per scontato.

## Risultato apprezzabile

`docker compose up` → si apre l'app, si fa login con l'admin iniziale (cambio password forzato), si naviga una shell vuota ma vera (sidebar, tema scuro/chiaro). Swagger attivo su `/api/docs`.

## MVP

### Backend

- [ ] **1.B1 — Skeleton e compose** (~3h): monorepo ([struttura](../infrastructure/build-system.md)), compose `db`+`web` con healthcheck, loader config (`config.yaml` + `.env`), `GET /api/health`. *Verifica: compose up, health verde.*
- [ ] **1.B2 — Utenti e bootstrap** (~2h): tabella `users` ([schema](../4-capabilities/database/schema.md)), hashing bcrypt, creazione admin iniziale da `.env` con `must_change_password`. *Verifica: riga admin nel DB via Adminer (profilo dev).*
- [ ] **1.B3 — Auth JWT** (~4h): login/refresh/logout/change-password con `typ`, rotazione jti, `token_version`, rate limit sul login ([auth](../4-capabilities/core/auth.md)). *Verifica: flusso completo da Swagger, refresh riusato → 401.*
- [ ] **1.B4 — Endpoint profilo** (~1h): `GET/PATCH /api/me` (lingua), 403 dedicato per `must_change_password`. *Verifica: da Swagger.*

### Frontend

- [ ] **1.F1 — Shell SPA** (~4h): SvelteKit SPA, pagina login, [Auth Manager](../4-capabilities/frontend/auth-manager.md) (single-flight sul refresh), sidebar statica, tema scuro/chiaro senza flash ([app-shell](../4-capabilities/frontend/app-shell.md)). *Verifica: login da browser, reload mantiene la sessione.*
- [ ] **1.F2 — Cambio password forzato + profilo minimo** (~2h): intercettazione del 403 dedicato → pagina di cambio obbligato; pagina profilo con cambio password e lingua. *Verifica: primo login admin → cambio obbligato.*

### Trasversali

- [ ] **1.T1 — CI minima** (~2h): GitHub Actions con ruff, mypy, eslint/svelte-check, build frontend ([ci](../infrastructure/ci.md)). *Verifica: PR con errore di lint → rossa.*

## Definition of Done

- [ ] Da zero: `cp .env.example .env` + compose up + login + cambio password, senza toccare altro.
- [ ] Swagger mostra Auth/Me/Health con modelli tipizzati.
- [ ] CI verde su `main`.

## Riferimenti

[deployment](../infrastructure/deployment.md) · [configuration](../infrastructure/configuration.md) · [auth](../4-capabilities/core/auth.md) · [security-posture](../2-architecture/security-posture.md)
