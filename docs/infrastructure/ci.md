# CI

> **Infrastruttura** · Audience: DevOps, developer.

Pipeline minima (GitHub Actions) su ogni push/PR: esegue i tool già scelti dal progetto — la CI non introduce regole nuove, rende reali quelle esistenti.

## Job

| Job | Comandi | Gate |
|---|---|---|
| Lint backend | `ruff check .` · `ruff format --check .` | bloccante |
| Typecheck backend | `mypy` (strict) | bloccante |
| Test backend | `pytest` (unit + contratto; integrazione con Postgres service) | bloccante |
| Lint frontend | `eslint` · `prettier --check` · `svelte-check` | bloccante |
| Build frontend | `npm run build` (include `build:plugins`) | bloccante |
| Build immagini | build di `watch-em-all` (app) e `watch-em-all-ops`; **su PR** push come `dev-<branch>` (vedi *Immagini dev*) | bloccante |
| Guardia CHANGELOG | la PR deve aggiornare `CHANGELOG.md` (ogni PR = una versione, INF-19) | bloccante |

La pipeline nasce in **fase 0** del [development flow](../development-flow/phase-00-pipeline.md) (build immagini, guardia CHANGELOG, publish dev e su tag) e **cresce col flusso**: linter e typecheck con il primo codice (fase 1), test di contratto e integrazione a regime (fase 12).

## Immagini dev (su PR)

Per **provare il container prima del merge**, un workflow costruisce le immagini a ogni **apertura/aggiornamento di PR** (anche draft) e le pubblica su GHCR con tag **`dev-<branch>`** (nome del branch sanificato), **sovrascritto** a ogni push: punta sempre all'ultima build di quel ramo. Più rami in volo → tag distinti, nessuna collisione.

- **Branch senza PR**: trigger manuale (`workflow_dispatch` con il branch in input) per generare `dev-<branch>` on-demand.
- **Niente tag per-commit**: per fissare una build esatta si usa il **digest** (`@sha256:…`), sempre disponibile.
- Le immagini `dev-*` sono **effimere**: il tag `dev-<branch>` viene **eliminato automaticamente alla chiusura della PR** — merge o abbandono — dal workflow `cleanup-dev-images.yml`, così i package non si riempiono di tag morti. Permanenti solo i tag di release `x.y.z` (mai toccati dalla pulizia).

Come installare una dev per provarla: [deployment](deployment.md#provare-unimmagine-di-sviluppo).

## Publish (su tag)

Workflow separato, attivato dai **tag `x.y.z`** (SemVer puro, senza prefisso `v`; INF-17): builda le tre immagini multi-stage e le pubblica su **GHCR**, poi crea la release GitHub con il **deploy kit** in allegato.

| Step | Cosa fa |
|---|---|
| Build & push | `watch-em-all` (app: ruoli web+worker) e `watch-em-all-ops` → `ghcr.io/<owner>/…:<tag>` (es. `1.2.0`; mai `latest`, INF-1) |
| Release + kit | allega alla release `compose.yml` (il compose di release) e `.env.example` — i **soli due file** che servono per installare ([deployment](deployment.md)) |

Il tag è l'unico trigger di pubblicazione: `main` verde non pubblica nulla — e il tag lo crea **l'owner a mano**, quando vuole una release (vedi *Tag e release* sotto). I **package GHCR sono pubblici** (come il repo): il pull lato utente è anonimo, nessuna autenticazione.

### Versioning del prodotto

Il prodotto segue **SemVer** (`MAJOR.MINOR.PATCH`) con una **versione unica per l'intero bundle** (core + plugin first-party, spediti insieme nelle immagini); è la regola INF-19.

| Parte | Quando si incrementa |
|---|---|
| **MAJOR** | breaking dell'API HTTP pubblica **o** schema DB non puramente additivo (migrazione manuale, DB-R4) |
| **MINOR** | nuove feature retrocompatibili (tipicamente la chiusura di una fase del [flow](../development-flow/README.md)) |
| **PATCH** | fix retrocompatibili |

- `0.x` durante lo sviluppo (**0.1** alla chiusura della fase 7, **1.0** alla fase 12 — milestone scelte nella PR che chiude quelle fasi); **ogni PR** porta un bump di versione + voce `CHANGELOG.md` (**1 MVP = 1 PR = 1 versione**), ma **i tag non sono per-PR**: li crea **l'owner a mano** quando vuole una release (vedi sotto), così il repo non si riempie di tag.
- `CHANGELOG.md` aggiornato nella **stessa PR** (è la guardia CHANGELOG della CI a imporlo).

### Tag e release (manuali)

Il tag `x.y.z` (SemVer puro, **senza prefisso `v`**) lo crea **l'owner a mano**, quando decide che è il momento di una release: **nessun workflow di auto-tag**. Il push del tag su GitHub innesca `publish.yml` (build+push delle immagini versionate su GHCR + release con il deploy kit allegato). Implementato in fase 0 (0.T9).

- I tag **non sono per-PR**: l'owner ne crea **quando vuole**; le versioni intermedie (per-PR) vivono solo nel CHANGELOG, senza tag — così il repo non si riempie di tag.
- **Procedura di release** (le *immutable releases* di GitHub sono attive di default: gli asset di una release pubblicata sono congelati): il tag si crea **da CLI** (`git tag x.y.z && git push origin x.y.z`) → la CI builda le immagini e **prepara una release in *bozza* con il kit già allegato** (la bozza è mutabile), poi si ferma → l'owner **scrive le note e clicca Publish dalla UI**. ⚠️ **Non** pubblicare una release a mano dalla UI: bloccheresti una release immutabile **senza kit**, e quella versione resterebbe **bruciata** (il tag diventa permanentemente riservato, non riusabile). Un guardrail nel workflow intercetta questo caso e fallisce con le istruzioni.
- La versione del tag è quella dell'ultima voce di `CHANGELOG.md` da pubblicare; può alzare MINOR/MAJOR quando la milestone lo merita (es. 0.1.0 alla fase 7, 1.0.0 alla 12).
- **Distinta** da: il `version` del manifest di un plugin (informativo, per-plugin) e l'`api_version` (intero, gate di compatibilità del contratto plugin) — entrambi ortogonali alla versione del prodotto.

## Note

- Il job di test backend usa un service container Postgres 16: i test di integrazione (catalog delta, alert engine, auth) girano su un DB reale effimero.
- I test di **contratto dei plugin** ([checklist](../plugin-development/checklist-and-testing.md)) girano per ogni plugin abilitato: uno scraper che rompe le regole dell'`external_id` fallisce la CI, non la produzione.
- Nessun deploy automatico verso le installazioni: la CI **pubblica** le immagini, l'aggiornamento resta una scelta dell'utente (`WEA_VERSION` nel `.env` + `pull`), coerente con la postura self-hosted.
- Politica: `main` sempre verde; le PR non si mergiano con job rossi. Dettagli di processo in [developer-rules](../developer-rules/README.md).
