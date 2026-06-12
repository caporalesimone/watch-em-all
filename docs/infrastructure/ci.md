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
| Build immagini | `docker compose build` (senza push) | bloccante |

## Publish (su tag)

Workflow separato, attivato dai **tag `v*`** (INF-17): builda le tre immagini multi-stage e le pubblica su **GHCR**, poi crea la release GitHub con il **deploy kit** in allegato.

| Step | Cosa fa |
|---|---|
| Build & push | `watch-em-all-web`, `watch-em-all-worker`, `watch-em-all-ops` → `ghcr.io/<owner>/…:<tag>` (es. `v1.2.0`; mai `latest`, INF-1) |
| Release + kit | allega alla release `compose.yml` (il compose di release) e `.env.example` — i **soli due file** che servono per installare ([deployment](deployment.md)) |

Il tag è l'unico trigger di pubblicazione: `main` verde non pubblica nulla — si pubblica una versione quando lo si decide.

### Versioning del prodotto

Il prodotto segue **SemVer** (`MAJOR.MINOR.PATCH`) con una **versione unica per l'intero bundle** (core + plugin first-party, spediti insieme nelle immagini); è la regola INF-19.

| Parte | Quando si incrementa |
|---|---|
| **MAJOR** | breaking dell'API HTTP pubblica **o** schema DB non puramente additivo (migrazione manuale, DB-R4) |
| **MINOR** | nuove feature retrocompatibili (tipicamente la chiusura di una fase del [flow](../development-flow/README.md)) |
| **PATCH** | fix retrocompatibili |

- `0.x` durante lo sviluppo (**0.1** alla fase 7, **1.0** alla fase 12, come già nel flow); il tag `vX.Y.Z` è **deliberato**, non automatico a ogni merge: a chiusura di fase o quando un gruppo di MVP forma un incremento utile.
- `CHANGELOG.md` aggiornato nella **stessa PR** che porta al tag.
- **Distinta** da: il `version` del manifest di un plugin (informativo, per-plugin) e l'`api_version` (intero, gate di compatibilità del contratto plugin) — entrambi ortogonali alla versione del prodotto.

## Note

- Il job di test backend usa un service container Postgres 16: i test di integrazione (catalog delta, alert engine, auth) girano su un DB reale effimero.
- I test di **contratto dei plugin** ([checklist](../plugin-development/checklist-and-testing.md)) girano per ogni plugin abilitato: uno scraper che rompe le regole dell'`external_id` fallisce la CI, non la produzione.
- Nessun deploy automatico verso le installazioni: la CI **pubblica** le immagini, l'aggiornamento resta una scelta dell'utente (`WEA_VERSION` nel `.env` + `pull`), coerente con la postura self-hosted.
- Politica: `main` sempre verde; le PR non si mergiano con job rossi. Dettagli di processo in [developer-rules](../developer-rules/README.md).
