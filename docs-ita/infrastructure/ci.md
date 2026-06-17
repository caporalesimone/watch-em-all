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

Workflow separato, attivato dai **tag `x.y.z`** (SemVer puro, senza prefisso `v`; INF-17): builda le **due** immagini multi-stage e le pubblica su **GHCR**. La **release GitHub** (con le note) la crea **l'owner** (UI o CLI); il **deploy kit non è allegato** alla release — vive nel repo e si scarica da lì ([deployment](deployment.md)).

| Step | Cosa fa |
|---|---|
| Build & push | `watch-em-all` (app: ruoli web+worker) e `watch-em-all-ops` → `ghcr.io/<owner>/…:<tag>` (es. `1.2.0`; mai `latest`, INF-1) |

Il tag è l'unico trigger di pubblicazione delle immagini: `main` verde non pubblica nulla — e il tag lo crea **l'owner a mano**, quando vuole una release (vedi *Tag e release* sotto). I **package GHCR sono pubblici** (come il repo): il pull lato utente è anonimo, nessuna autenticazione.

### Versioning del prodotto

Il prodotto segue **SemVer** (`MAJOR.MINOR.PATCH`) con una **versione unica per l'intero bundle** (core + plugin first-party, spediti insieme nelle immagini); è la regola INF-19.

| Parte | Quando si incrementa |
|---|---|
| **MAJOR** | breaking dell'API HTTP pubblica **o** schema DB non puramente additivo (migrazione manuale, DB-R4) |
| **MINOR** | nuove feature retrocompatibili (tipicamente la chiusura di una fase del [flow](../development-flow/README.md)) |
| **PATCH** | fix retrocompatibili |

- `0.x` durante lo sviluppo: la **chiusura di una fase** alza il **MINOR** (la fase 1 — Fondamenta — porta a **0.1.0**) e **1.0** segna la v1 (fase 12) — milestone decise nella PR che chiude la fase; **ogni PR** porta un bump di versione + voce `CHANGELOG.md` (**1 MVP = 1 PR = 1 versione**; una fase sviluppata in un colpo solo consolida le sue voci sotto la versione di fase), ma **i tag non sono per-PR**: li crea **l'owner a mano** quando vuole una release (vedi sotto), così il repo non si riempie di tag.
- `CHANGELOG.md` aggiornato nella **stessa PR** (è la guardia CHANGELOG della CI a imporlo).

### Fonte unica della versione (source of truth)

La versione del prodotto ha **un'unica source of truth: il tag git**. Non è scritta a mano in alcun file versionato — `pyproject.toml` e `package.json` tengono un `version` **placeholder inerte** (non pubblichiamo pacchetti su PyPI/npm): la versione reale è **calcolata in build** da `git describe --tags --always` e **cucinata nell'immagine** (file `/app/VERSION`). Quindi:

- **su un tag** (release): `git describe` restituisce il tag puro → `x.y.z`;
- **fuori da un tag** (dev, branch, build locale): `x.y.z-N-g<sha>` ("N commit dopo la release `x.y.z`, al commit `<sha>`") — così ogni build mostra una **versione reale e ricostruibile**, mai un placeholder come `0.0.0`.

L'app **espone** questa versione a runtime: `GET /api/health` la riporta (e così il titolo di Swagger e il footer della UI). Una sola formula, calcolata in un solo punto (il Dockerfile), identica per release, dev e locale.

Il **`CHANGELOG.md` non è la fonte: è solo verificato.** Una guardia in `publish.yml` controlla, al push del tag, che il tag coincida con la versione dell'**ultima voce** del `CHANGELOG.md`; se divergono la pubblicazione fallisce (impedisce il drift "taggo prima di aver finalizzato il changelog"). `WEA_VERSION` nel `.env` è cosa diversa ancora: è la **scelta dell'operatore** su quale immagine far girare (il tag da `pull`), non la versione del prodotto.

> Note di build: `git describe` richiede la storia git nel contesto — `.git/` è incluso nel build context (non in `.dockerignore`) e i workflow fanno `fetch-depth: 0` (il checkout di default è shallow e senza tag). `git` è installato solo nello **stage di build** (multi-stage): l'immagine finale contiene solo la stringa di versione, non `.git`. `--dirty` è omesso di proposito: il build context è una copia filtrata dell'albero (esclude cartelle tracciate come `docs/`), quindi un flag "dirty" sul working tree non avrebbe senso — `describe` legge solo i ref di `.git`, senza working tree.

### Tag e release (manuali)

Il tag `x.y.z` (SemVer puro, **senza prefisso `v`**) lo crea **l'owner a mano**, quando decide che è il momento di una release: **nessun workflow di auto-tag**. Il push del tag su GitHub innesca `publish.yml` (build+push delle immagini versionate su GHCR). Implementato in fase 0 (0.T9).

- I tag **non sono per-PR**: l'owner ne crea **quando vuole**; le versioni intermedie (per-PR) vivono solo nel CHANGELOG, senza tag — così il repo non si riempie di tag.
- **Procedura di release**: il tag lo crea l'owner **dalla UI di GitHub** (pubblicando una release con le sue note) **o da CLI** (`git tag x.y.z && git push origin x.y.z`); il push del tag fa partire `publish.yml` che builda e pusha le immagini versionate. Il **deploy kit non è allegato alla release** — vive nel repo e l'utente lo scarica al tag della versione ([deployment](deployment.md)). Non essendoci asset sulla release, le *immutable releases* di GitHub non impongono nulla: la release si può creare liberamente dalla UI.
- La versione del tag è quella dell'ultima voce di `CHANGELOG.md` da pubblicare; può alzare MINOR/MAJOR quando la milestone lo merita (es. 0.1.0 alla fase 1, 1.0.0 alla fase 12). **`publish.yml` verifica** che il tag coincida con quella voce e fallisce in caso di drift (vedi *Fonte unica della versione*).
- **Distinta** da: il `version` del manifest di un plugin (informativo, per-plugin) e l'`api_version` (intero, gate di compatibilità del contratto plugin) — entrambi ortogonali alla versione del prodotto.

## Note

- Il job di test backend usa un service container Postgres 16: i test di integrazione (catalog delta, alert engine, auth) girano su un DB reale effimero.
- I test di **contratto dei plugin** ([checklist](../plugin-development/checklist-and-testing.md)) girano per ogni plugin abilitato: uno scraper che rompe le regole dell'`external_id` fallisce la CI, non la produzione.
- Nessun deploy automatico verso le installazioni: la CI **pubblica** le immagini, l'aggiornamento resta una scelta dell'utente (`WEA_VERSION` nel `.env` + `pull`), coerente con la postura self-hosted.
- Politica: `main` sempre verde; le PR non si mergiano con job rossi. Dettagli di processo in [developer-rules](../developer-rules/README.md).
