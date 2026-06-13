# Fase 0 — Pipeline e processo

> Stato: 🔄 in corso · Prerequisiti: nessuno · [Indice del flusso](README.md)

## Obiettivo

**Il flusso di sviluppo prima del prodotto.** Repo, dev container, container Docker (anche vuoti), workflow GitHub, immagine dev sul branch, release sul tag, deploy kit: l'intera catena branch → PR → immagine dev → merge → tag → install pull-based viene costruita e **rodata per intero** con container segnaposto. Quando questa fase è chiusa, tutto il processo è pronto: da lì in poi si può iniziare a pensare al codice.

## Risultato apprezzabile

Apri un branch e la CI pubblica `dev-<branch>` su GHCR; lo provi con il compose puntando `WEA_VERSION`. Al merge l'owner crea il tag `v0.0.1`: su una **macchina pulita con il solo Docker**, scaricando i due file del deploy kit, `pull` + `up` tira su lo stack — la pagina è un segnaposto, ma il processo è quello definitivo.

## Mock dichiarati

I tre container applicativi sono **stub**: nessuna logica di prodotto.

| Stub | Cosa fa in questa fase | Chi lo sostituisce |
|---|---|---|
| `web` | pagina statica "coming soon" + `GET /api/health` che risponde sempre 200 | 1.B2 (app FastAPI reale) |
| `worker` | loop che tocca il file di heartbeat e logga un tick al minuto | 4.B1 (worker reale) |
| `ops` | `postgres:16` + `backup.sh`/`export.sh`/`restore.sh` segnaposto ("non ancora implementato", exit 1) | 1.T2/1.T3 (script reali) |

## MVP

### Trasversali

- [x] **0.T1 — Skeleton del repo + CHANGELOG** (~1h): alberatura del monorepo ([struttura](../infrastructure/build-system.md)), `.gitignore`, `CHANGELOG.md` inizializzato, README stub con le sezioni operative segnaposto (si riempiono man mano, INF-18). *Verifica: struttura committata, `main` protetto da PR.*
- [x] **0.T2 — Dev container** (~1h): `.devcontainer/` (Dockerfile con Python 3.12+Poetry, Node 22+npm, git, docker CLI; socket Docker dell'host; forward 8080/8081; post-create tollerante) ([dev-container](../infrastructure/dev-container.md), INF-15). Niente `gh` nel container: git/GitHub si usano **dall'host**. *Verifica: "Reopen in Container" su host con solo Docker → poetry/npm/compose funzionano da dentro.*
- [x] **0.T3 — Container stub `web`** (~1h): Dockerfile multi-stage minimale (INF-5) che serve la pagina segnaposto e `GET /api/health`. **Mock**: health sempre 200, nessuna app. *Verifica: `docker run` → pagina e health raggiungibili.*
- [x] **0.T4 — Container stub `worker` e `ops`** (~1h): worker = loop heartbeat (file + log); ops = `postgres:16` + script segnaposto in `ops/`. **Mock**: nessuna logica reale. *Verifica: heartbeat avanza; `run --rm ops backup.sh` → messaggio chiaro "non ancora implementato".*
- [ ] **0.T5 — Compose di sviluppo** (~1h): `docker-compose.yml` con `db`+`web`+`worker` (+`adminer` profilo `dev`, `ops` profilo `ops`), healthcheck e log rotation (INF-2) ([deployment](../infrastructure/deployment.md)). *Verifica: `compose up` → tutti healthy, segnaposto nel browser.*
- [ ] **0.T6 — CI di base su PR** (~1h): workflow GitHub Actions che builda le tre immagini a ogni PR + **guardia CHANGELOG** (PR rossa se `CHANGELOG.md` non è aggiornato, INF-19) ([ci](../infrastructure/ci.md)). I linter arrivano col codice (1.T1). *Verifica: PR senza voce CHANGELOG → rossa; con voce → verde.*
- [ ] **0.T7 — Immagini dev sul branch** (~1h): job che pubblica `web`/`worker`/`ops` su GHCR con tag **`dev-<branch>`** (mutabile, su PR e `workflow_dispatch`) ([ci — immagini dev](../infrastructure/ci.md#immagini-dev-su-pr)). *Verifica: push sul branch → `docker pull` anonimo di `dev-<branch>` funziona.*
- [ ] **0.T8 — Tag automatico di fine fase** (~1h): workflow che al push su `main` legge l'ultima voce di `CHANGELOG.md` e, **solo se contiene il marker di chiusura fase** (`Closes phase N`), crea il tag `vX.Y.Z` con la versione di quella voce — niente tag per-PR: **13 fasi = 13 tag** ([ci — tag di fine fase](../infrastructure/ci.md#tag-di-fine-fase-automatico), INF-19). *Verifica: merge con marker → tag creato; merge senza marker → nessun tag.*
- [ ] **0.T9 — Publish su tag + deploy kit** (~1h): workflow su tag `v*` → push delle tre immagini versionate su GHCR + release GitHub con `deploy/compose.yml` (immagini, niente `build:`, mount di override `config.yaml` commentato) e `.env.example` con `WEA_VERSION` allegati ([ci — publish](../infrastructure/ci.md), INF-17). *Verifica: tag → release con i due file, immagini taggate `vX.Y.Z`.*
- [ ] **0.T10 — Rodaggio end-to-end del processo** (~1h): il giro completo, una volta per intero: branch → PR con bump+CHANGELOG → prova dell'immagine `dev-<branch>` via `WEA_VERSION` → merge dell'owner; la PR di rodaggio **chiude la fase 0** (marker nel CHANGELOG) → tag automatico (0.T8) → publish (0.T9) → install pull-based su macchina pulita (due file, nessun sorgente); README aggiornato con i comandi usati (INF-18). *Verifica: segnaposto raggiungibile sulla macchina pulita partendo dal solo deploy kit.*

## Definition of Done

- [ ] Il ciclo **branch → PR (bump+CHANGELOG) → immagine `dev-<branch>` → merge dell'owner → chiusura di fase → tag automatico → release → install pull-based** è stato percorso per intero almeno una volta. I tag nascono **solo a fine fase** (13 fasi = 13 tag); le versioni intermedie vivono nel CHANGELOG.
- [ ] Su una macchina pulita con il **solo Docker**, i due file del deploy kit bastano per tirare su lo stack (INF-17) — anche se l'app è un segnaposto.
- [ ] Il dev container funziona: da qui in poi **tutto lo sviluppo avviene lì dentro** (INF-15).
- [ ] Ogni stub è dichiarato (tabella sopra) e ha l'MVP che lo sostituirà.
- [ ] [docs-eng](../../docs-eng/) aggiornata in inglese con la sola parte implementata in questa fase (DOC-12).

## Riferimenti

[ci](../infrastructure/ci.md) · [deployment](../infrastructure/deployment.md) · [dev-container](../infrastructure/dev-container.md) · [build-system](../infrastructure/build-system.md) · [developer-rules (processo)](../developer-rules/README.md)
