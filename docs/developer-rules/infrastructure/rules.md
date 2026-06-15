# Developer Rules — Infrastruttura

> Vincolanti per Docker, configurazione e gestione dipendenze. Docs: [infrastructure/](../../infrastructure/deployment.md).

## Docker e compose

- **INF-1** — Immagini **pinnate** (mai `latest`): `postgres:16`, `adminer:4`, base images con tag esplicito.
- **INF-2** — Log rotation su ogni servizio applicativo (`max-size`/`max-file`); healthcheck su `db`, `web` (endpoint health) e `worker` (file heartbeat).
- **INF-3** — Strumenti di debug (Adminer e simili) **solo dietro profilo `dev`**: il compose di default deve essere production-shaped.
- **INF-4** — Mount read-only dove possibile (`config.yaml:ro`); nessun bind-mount di codice in produzione.
- **INF-5** — Dockerfile multi-stage: build del frontend e installazione Poetry separate dallo stage finale; immagini finali senza toolchain di build.

## Configurazione e segreti

- **INF-6** — Gerarchia rispettata: bootstrap in `config.yaml`, segreti in `.env`, tutto il resto nel DB ([configuration](../../infrastructure/configuration.md)). Mai parametri operativi nuovi in `config.yaml` "per comodità".
- **INF-7** — `.env` **mai** committato; `.env.example` sempre aggiornato a ogni chiave nuova (stessa PR).
- **INF-8** — Nessun segreto nei log, negli errori API o nei messaggi di commit. I campi secret dei plugin restano write-only end-to-end.
- **INF-9** — Default sicuri: ogni impostazione di sistema nuova nasce con un default prudente e documentato ([SystemSettings](../../4-capabilities/contracts/scheduling-models.md)).

## Dipendenze

- **INF-10** — Backend: **un solo `pyproject.toml` alla root** con **un solo `poetry.lock` committato** (niente lockfile per-package: web e worker condividono l'ambiente e i plugin); dipendenze nuove motivate nella PR (preferire la standard library quando ragionevole — es. l'invio SMTP). Dipendenze dei plugin in **gruppi opzionali** del pyproject unico, installati dai Dockerfile che li servono.
- **INF-11** — Frontend: `package-lock.json` committato; niente dipendenze UI che dupplicano il design system.
- **INF-12** — Aggiornamenti di dipendenze in PR dedicate (non mescolati alle feature).

## Host e ambienti

- **INF-15** — **Zero-install sull'host**: il target di hosting è **Linux** (WSL2 in locale o server dedicato) e l'unico prerequisito è Docker Engine + Compose. Nessun software di sviluppo o runtime si installa mai sull'host — né su quello di sviluppo né su quello di hosting: la toolchain vive **solo nei container** (sviluppo: [dev container](../../infrastructure/dev-container.md); hosting: immagini multi-stage autosufficienti, INF-5). Un'istruzione di setup che inizia con "installa X sull'host" (X ≠ Docker) è una violazione.
- **INF-17** — **Release pull-based**: si installa **senza sorgenti**. Il workflow di publish ([ci](../../infrastructure/ci.md)), attivato dai tag `x.y.z` (SemVer puro, senza prefisso `v`), pubblica le due immagini — `watch-em-all` (app: ruoli `web` e `worker`) e `watch-em-all-ops` — su GHCR. Il **deploy kit** (`deploy/compose.yml` + `.env.example`) **vive nel repo** (non è allegato alla release: l'utente lo scarica al tag della versione): quei **due file devono sempre bastare** per un'installazione completa. Ogni modifica che introduce un nuovo file host, mount o variabile aggiorna il deploy kit **nella stessa PR**. `config.yaml` di default vive nelle immagini; l'override locale è un mount opzionale.
- **INF-18** — **Il `README.md` del repo è il manuale operativo completo**: contiene (o linka in un punto solo) **tutte** le istruzioni per deployare il sito e farne manutenzione — installazione pull-based passo-passo, aggiornamento di versione, backup/export/ripristino con **tutti i comandi e gli script disponibili**, esposizione opzionale a Internet, troubleshooting di base (health, heartbeat, log). Ogni nuovo comando o script operativo si aggiunge al README **nella stessa PR** che lo introduce; un'installazione da zero deve riuscire leggendo solo il README (verificato alla release, fase 12).
- **INF-19** — **Versioning del prodotto**: **SemVer** (`MAJOR.MINOR.PATCH`), **versione unica per il bundle** (core + plugin first-party). **Ogni PR porta un bump di versione e una voce `CHANGELOG.md`** (senza, non è mergiabile) — **1 MVP = 1 PR = 1 versione**. I **tag non sono per-PR**: il tag `x.y.z` (SemVer puro, **senza prefisso `v`**) lo crea **l'owner a mano** quando vuole una release, e il push del tag genera le immagini di release (il deploy kit vive nel repo, INF-17). **MAJOR** su breaking dell'API pubblica o schema DB non additivo (DB-R4). Le immagini **dev** di anteprima sono taggate `dev-<branch>` (mutabili, su PR; vedi [ci](../../infrastructure/ci.md#immagini-dev-su-pr)). Distinta dall'`api_version` dei plugin (gate di contratto) e dal `version` informativo del manifest. Dettaglio: [ci](../../infrastructure/ci.md#tag-e-release-manuali).

## Dati

- **INF-13** — Schema: additivo con `CREATE ... IF NOT EXISTS`; i breaking change richiedono script SQL manuale documentato (DB-R4). **Vietato** il drop&recreate dell'intero schema: `price_history` non è ricostruibile. (Unica eccezione: il ripristino da backup, che *è* lo stato da riportare in vita — [backup-and-restore](../../infrastructure/backup-and-restore.md).)
- **INF-14** — Qualunque script di manutenzione che tocca dati di produzione si scrive idempotente e si prova prima su un dump.
- **INF-16** — Gli script di **backup/export/restore** (`ops/`, cucinati nell'immagine `ops`, esecuzione manuale con `docker compose run --rm ops …` — [backup-and-restore](../../infrastructure/backup-and-restore.md)) si aggiornano **nella stessa PR** di ogni modifica che tocca ciò che salvano (nuovi file di configurazione, nuovi volumi, cambi di formato); `restore.sh` chiede sempre conferma e verifica l'archivio prima di toccare il DB.
