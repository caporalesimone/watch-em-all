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

- **INF-10** — Backend: Poetry con lock committato; dipendenze nuove motivate nella PR (preferire la standard library quando ragionevole — es. l'invio SMTP). Dipendenze dei plugin nei gruppi opzionali dei package `web`/`worker`.
- **INF-11** — Frontend: `package-lock.json` committato; niente dipendenze UI che dupplicano il design system.
- **INF-12** — Aggiornamenti di dipendenze in PR dedicate (non mescolati alle feature).

## Dati

- **INF-13** — Schema: additivo con `CREATE ... IF NOT EXISTS`; i breaking change richiedono script SQL manuale documentato (DB-R4). **Vietato** il drop&recreate dell'intero schema: `price_history` non è ricostruibile.
- **INF-14** — Qualunque script di manutenzione che tocca dati di produzione si scrive idempotente e si prova prima su un dump.
