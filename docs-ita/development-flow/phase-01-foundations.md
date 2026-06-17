# Fase 1 — Fondamenta

> Stato: ☐ da iniziare · Prerequisiti: Fase 0 · [Indice del flusso](README.md)

## Obiettivo

Lo scheletro vivo: l'app vera al posto degli stub di fase 0 — database, autenticazione, shell della SPA. Tutto ciò che le fasi successive danno per scontato. La pipeline c'è già (fase 0): ogni MVP qui sotto nasce come PR con la sua immagine `dev-<branch>` da provare.

## Risultato apprezzabile

`docker compose up` → si apre l'app, si fa login con l'admin iniziale (cambio password forzato), si naviga una shell vuota ma vera (sidebar, tema scuro/chiaro). Swagger attivo su `/api/docs`.

## MVP

### Backend

- [ ] **1.B1 — Loader di configurazione** (~1h): lettura `config.yaml` + `.env`, interpolazione `${VAR}`, validazione all'avvio ([configuration](../infrastructure/configuration.md)); legge anche la **versione del prodotto** cucinata a build (file `/app/VERSION`, source of truth = tag git, vedi 1.T4). *Verifica: unit test del loader (chiave mancante → errore chiaro).*
- [ ] **1.B2 — App FastAPI + health** (~1h): app vera nel container `web` (sostituisce lo stub 0.T3), `GET /api/health` con check del DB **e la versione del prodotto**, Swagger su `/api/docs`. *Verifica: compose up → health verde con la versione attesa; DB giù → 503.*
- [ ] **1.B3 — Utenti e bootstrap** (~1h): tabella `users` ([schema](../4-capabilities/database/schema.md)), hashing bcrypt, creazione admin iniziale da `.env` con `must_change_password`. *Verifica: riga admin nel DB via Adminer (profilo dev).*
- [ ] **1.B4 — Login e logout** (~1h): `POST /api/auth/login` (JWT `typ=access`) + logout. **Mock**: niente refresh — la sessione dura quanto l'access token; lo sostituisce 1.B5. *Verifica: login da Swagger → token valido sulle route protette.*
- [ ] **1.B5 — Refresh con rotazione** (~1h): refresh token, rotazione `jti`, `token_version`, riuso → 401 ([auth](../4-capabilities/core/auth.md)). *Verifica: refresh riusato → 401; logout invalida la famiglia.*
- [ ] **1.B6 — Change-password + rate limit** (~1h): cambio password, 403 dedicato per `must_change_password`, rate limit sul login. *Verifica: flusso completo da Swagger; brute-force → 429.*
- [ ] **1.B7 — Endpoint profilo** (~1h): `GET/PATCH /api/me` (lingua). *Verifica: da Swagger.*

### Frontend

- [ ] **1.F1 — Scaffold SPA + i18n + tema** (~1h): SvelteKit SPA, **svelte-i18n con `en.json` (+ `it.json`)** fin dalla prima pagina — nessuna stringa cablata (FE-13) —, tema scuro/chiaro senza flash ([app-shell](../4-capabilities/frontend/app-shell.md)). *Verifica: pagina segnaposto tradotta, nei due temi, senza flash al reload.*
- [ ] **1.F2 — Login + Auth Manager** (~1h): pagina login, [Auth Manager](../4-capabilities/frontend/auth-manager.md) con single-flight sul refresh. *Verifica: login da browser, reload mantiene la sessione.*
- [ ] **1.F3 — Shell con sidebar** (~1h): layout protetto, sidebar statica, route guard. *Verifica: senza sessione → redirect al login; navigazione fluida.*
- [ ] **1.F4 — Cambio password forzato** (~1h): intercettazione del 403 dedicato → pagina di cambio obbligato. *Verifica: primo login admin → cambio obbligato, poi accesso normale.*
- [ ] **1.F5 — Pagina profilo minima** (~1h): cambio password e lingua. *Verifica: cambio lingua → UI tradotta subito.*

### Trasversali

- [ ] **1.T1 — CI: lint e typecheck** (~1h): ruff, mypy, eslint/svelte-check e build frontend nel workflow di fase 0 ([ci](../infrastructure/ci.md)). *Verifica: PR con errore di lint → rossa.*
- [ ] **1.T2 — `backup.sh` + `export.sh` reali** (~1h): sostituiscono i segnaposto di 0.T4 — dump + `.env` (+ `config.yaml` se override locale) in archivio datato su `backups/` ([backup-and-restore](../infrastructure/backup-and-restore.md), INF-16). *Verifica: archivio creato con dump e file di bootstrap dentro.*
- [ ] **1.T3 — `restore.sh` reale** (~1h): verifica dell'archivio, conferma esplicita, rifiuto se lo stack web/worker è attivo. *Verifica: backup → `down -v` → `up` → restore → login con gli stessi dati e config.*
- [ ] **1.T4 — Versione: source of truth dal tag** (~1h): la versione del prodotto si calcola a build da `git describe --tags --always` (tag puro in release, `x.y.z-N-g<sha>` in dev — mai `0.0.0`) e si cuoce nell'immagine (`/app/VERSION`); `git` nello stage di build, `.git` nel context, `fetch-depth: 0` nei workflow. Guardia in `publish.yml`: il tag deve coincidere con l'ultima voce del `CHANGELOG.md` (CHANGELOG **solo verificato**, non fonte). `pyproject.toml`/`package.json` con `version` placeholder inerte ([ci](../infrastructure/ci.md#fonte-unica-della-versione-source-of-truth)). *Verifica: build su un tag → `/api/health` mostra `x.y.z`; build dev → `x.y.z-N-g<sha>`; tag ≠ CHANGELOG → publish rosso.*

## Definition of Done

- [ ] Da zero: `cp .env.example .env` + compose up + login + cambio password, senza toccare altro.
- [ ] Gli stub di fase 0 per `web` e per gli script `ops` sono **sostituiti dall'app reale** (resta stub solo il worker, fino alla fase 4).
- [ ] Una release di questa fase, installata pull-based dal deploy kit, mostra il login reale (INF-17).
- [ ] Il ciclo backup → distruzione volume → restore riproduce un'installazione identica.
- [ ] Swagger mostra Auth/Me/Health con modelli tipizzati.
- [ ] CI verde su `main` con i linter attivi.
- [ ] [docs](../../docs/) aggiornata in inglese con la sola parte implementata in questa fase (DOC-12).

## Riferimenti

[deployment](../infrastructure/deployment.md) · [configuration](../infrastructure/configuration.md) · [auth](../4-capabilities/core/auth.md) · [security-posture](../2-architecture/security-posture.md)
