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
- [ ] **1.T2 — Dev container** (~2h): `.devcontainer/` (Dockerfile con Python 3.12+Poetry, Node LTS+npm, git, docker CLI; socket Docker dell'host; devcontainer.json con forward 8080/8081) ([dev-container](../infrastructure/dev-container.md), INF-15). *Verifica: "Reopen in Container" su host con solo Docker → poetry/npm/compose funzionano da dentro; nessuna toolchain richiesta sull'host.*
- [ ] **1.T3 — Immagine ops: backup/export/restore** (~2h): `ops/backup.sh`, `ops/export.sh`, `ops/restore.sh`; immagine `ops` (`postgres:16` + script, `packages/ops/Dockerfile`); servizio effimero nel compose con mount di `backups/` (gitignorata) e dei file di bootstrap locali ([backup-and-restore](../infrastructure/backup-and-restore.md), INF-16). *Verifica: backup → `down -v` → `up` → restore → login con gli stessi dati e config; restore con stack web/worker attivo → rifiuta.*
- [ ] **1.T4 — Pipeline di publish + deploy kit** (~3h): workflow su tag `v*` → build e push di `web`/`worker`/`ops` su GHCR; `deploy/compose.yml` (immagini, niente `build:`, `config.yaml` di default nelle immagini con mount di override commentato) e `.env.example` con `WEA_VERSION`, allegati alla release; README del repo con le istruzioni complete di install e manutenzione ([ci](../infrastructure/ci.md), [deployment](../infrastructure/deployment.md), INF-17/INF-18). *Verifica: tag `v0.1.0-alpha` → su una macchina pulita con il **solo Docker**, scaricando i due file del kit: `pull` + `up` → login funzionante, **senza sorgenti**.*

## Definition of Done

- [ ] Da zero: `cp .env.example .env` + compose up + login + cambio password, senza toccare altro.
- [ ] Su un host Linux/WSL2 con il **solo Docker** si sviluppa (dev container) e si hosta: nessun altro software richiesto (INF-15).
- [ ] **Distribuzione provata**: un tag pubblica le immagini e il deploy kit; l'installazione pull-based (due file, nessun sorgente) funziona su macchina pulita (INF-17).
- [ ] Il README del repo basta da solo per installare e manutenere (INF-18).
- [ ] Il ciclo backup → distruzione volume → restore riproduce un'installazione identica.
- [ ] Swagger mostra Auth/Me/Health con modelli tipizzati.
- [ ] CI verde su `main`.
- [ ] [docs-eng](../../docs-eng/) aggiornata in inglese con la sola parte implementata in questa fase (DOC-12).

## Riferimenti

[deployment](../infrastructure/deployment.md) · [configuration](../infrastructure/configuration.md) · [auth](../4-capabilities/core/auth.md) · [security-posture](../2-architecture/security-posture.md)
