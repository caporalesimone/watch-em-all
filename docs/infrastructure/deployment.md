# Deployment (Docker)

> **Infrastruttura** · Audience: DevOps, system engineer. Snippet di configurazione ammessi (deroga dichiarata alle regole di layer).

> Questo documento è il **riferimento**; il manuale operativo per l'utente finale è il **`README.md` del repo**, che per regola (INF-18) contiene tutte le istruzioni di deploy e manutenzione con tutti i comandi e gli script disponibili, e si aggiorna a ogni nuovo comando introdotto.

## Requisiti dell'host

Il portale è hostato su **Linux**: in locale dentro **WSL2** oppure su un **server dedicato**. L'unico prerequisito è **Docker Engine + Compose plugin** — sull'host non si installa alcun software di sviluppo o runtime (niente Python, Node, psql: tutto vive nei container, INF-15). Per lo sviluppo vale lo stesso principio tramite il [dev container](dev-container.md); le immagini di hosting sono multi-stage e autosufficienti (frontend buildato dentro l'immagine `web`, INF-5).

## Installazione: pull, non build

Il deploy è **pull-based** (INF-17): la CI pubblica le immagini su GHCR a ogni tag ([ci](ci.md)) e l'utente **non scarica mai i sorgenti** — solo il **deploy kit**, due file allegati alla release:

| File | Ruolo |
|---|---|
| `compose.yml` | il compose di release: referenzia le immagini pubblicate, nessun `build:` |
| `.env.example` | template dei segreti + versione delle immagini (`WEA_VERSION`) |

```bash
mkdir watchemall && cd watchemall
curl -LO https://github.com/<owner>/watch-em-all/releases/latest/download/compose.yml
curl -LO https://github.com/<owner>/watch-em-all/releases/latest/download/.env.example
cp .env.example .env                  # poi compilare i valori
docker compose pull && docker compose up -d
```

Repo e package GHCR sono **pubblici**: il `pull` è **anonimo**, nessun `docker login` necessario (scelta di distribuzione, Q6). Le immagini pubblicate (pinnate per versione, mai `latest` — INF-1):

| Immagine | Contenuto |
|---|---|
| `ghcr.io/<owner>/watch-em-all:<ver>` | l'app: FastAPI + SPA buildata + tutti i plugin first-party + dispatcher/runner. **Un'unica immagine, due ruoli** scelti dal comando: `web` (API + SPA) e `worker` (scheduler + manutenzione) |
| `ghcr.io/<owner>/watch-em-all-ops:<ver>` | `postgres:16` + script di [backup/export/restore](backup-and-restore.md) |

**`config.yaml`**: il default è **dentro l'immagine** — non serve alcun file locale. Per personalizzarlo si crea una copia accanto al compose e la si monta sopra quella dell'immagine (`./config.yaml:/app/config.yaml:ro`, riga già pronta e commentata nel compose di release): il mount vince, l'immagine resta il fallback.

**Plugin**: il set di plugin è fissato **a build dell'immagine** (il bundle frontend è cucinato dentro); le immagini pubblicate includono **tutti i plugin first-party abilitati**, e il controllo fine resta runtime (sospensione scraper, interruttore globale notifier PCFG-R8). Un set custom richiede la build da sorgenti (percorso developer, [build-system](build-system.md)).

## Servizi

| Servizio | Ruolo | Esposizione |
|---|---|---|
| `db` | PostgreSQL 16, unico stato del sistema | solo rete interna |
| `web` | FastAPI + bundle SPA; API, auth, scrape on-demand | `:8080` |
| `worker` | Dispatcher + runner seriale scraper, alert, summary, manutenzione giornaliera | nessuna |
| `ops` | Script di backup/export/restore, **effimero** (`run --rm`, profilo `ops`) | nessuna |
| `adminer` | Ispezione DB dal browser | `:8081`, **solo profilo `dev`** |

`web` e `worker` sono **due servizi dalla stessa immagine** `watch-em-all` (ruolo scelto dal `command`); comunicano **solo tramite il DB**, entrambi attendono `db` healthy e garantiscono lo schema all'avvio (idempotente: non serve ordinarli tra loro).

## compose.yml (release, il file del deploy kit)

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_USER: "${POSTGRES_USER}"
      POSTGRES_PASSWORD: "${POSTGRES_PASSWORD}"
      POSTGRES_DB: "${POSTGRES_DB}"
    volumes: ["pgdata:/var/lib/postgresql/data"]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped
    logging: &logging
      driver: json-file
      options: { max-size: "10m", max-file: "3" }

  web:
    image: ghcr.io/<owner>/watch-em-all:${WEA_VERSION}
    command: ["web"]
    ports: ["8080:8080"]
    # config.yaml di default incluso nell'immagine; per personalizzarlo:
    # volumes: ["./config.yaml:/app/config.yaml:ro"]
    env_file: [.env]
    depends_on:
      db: { condition: service_healthy }
    healthcheck:
      test: ["CMD-SHELL", "curl -fsS http://localhost:8080/api/health || exit 1"]
      interval: 30s
      timeout: 5s
      retries: 3
    restart: unless-stopped
    logging: *logging

  worker:
    image: ghcr.io/<owner>/watch-em-all:${WEA_VERSION}
    command: ["worker"]
    # volumes: ["./config.yaml:/app/config.yaml:ro"]   # come per web, opzionale
    env_file: [.env]
    depends_on:
      db: { condition: service_healthy }
    healthcheck:
      # heartbeat: il worker tocca questo file a ogni tick (CRON-R7)
      test: ["CMD-SHELL", "test $(($(date +%s) - $(stat -c %Y /tmp/worker-heartbeat))) -lt 180"]
      interval: 60s
      timeout: 5s
      retries: 3
    restart: unless-stopped
    logging: *logging

  ops:
    image: ghcr.io/<owner>/watch-em-all-ops:${WEA_VERSION}
    profiles: [ops]                      # mai in esecuzione da solo: docker compose run --rm ops …
    env_file: [.env]
    volumes:
      - ./backups:/backups               # destinazione archivi
      - ./.env:/host/.env:ro             # incluso nel backup
      # - ./config.yaml:/host/config.yaml:ro   # se esiste un override locale, va nel backup
    depends_on:
      db: { condition: service_healthy }

  adminer:
    image: adminer:4
    ports: ["8081:8080"]
    profiles: [dev]
    depends_on:
      db: { condition: service_healthy }
    restart: unless-stopped

volumes:
  pgdata:
```

Note: niente campo `version` (deprecato in Compose v2); immagini pinnate via `WEA_VERSION` nel `.env`; log rotation ovunque. L'interpolazione `${VAR}` **dentro** `config.yaml` è fatta dal loader applicativo all'avvio, non da Docker (che interpola solo il compose file). Nel repo esiste anche il **compose di sviluppo** (`docker-compose.yml`, con `build:` al posto di `image:`): è il percorso developer, usato dal [dev container](dev-container.md) — i due file condividono la stessa forma.

## Avvio

```bash
cp .env.example .env            # poi compilare i valori
docker compose up -d            # produzione (senza adminer)
```

Primo avvio: lo schema viene creato, l'admin iniziale nasce con la password di `ADMIN_INITIAL_PASSWORD` e cambio forzato al primo login.

## Salute e monitoraggio

- `GET /api/health` → 200 se app viva e DB raggiungibile (include l'età dell'heartbeat del worker a scopo informativo), altrimenti 503.
- Il worker è sorvegliato dal **file di heartbeat** (healthcheck sopra) e dalla riga di heartbeat nel log di sistema (pagina admin).

## Esposizione a Internet (opzionale)

La postura del progetto accetta **HTTP su LAN** ([security posture](../2-architecture/security-posture.md)). Se si espone l'installazione a Internet, mettere davanti un reverse proxy con TLS; esempio con Caddy:

```
watchemall.example.com {
    reverse_proxy localhost:8080
}
```

## Backup, export e ripristino

Script versionati in `ops/` e **cucinati nell'immagine `ops`**, eseguiti **a mano** come container effimero — dettagli, regole e cosa contengono gli archivi in [backup-and-restore.md](backup-and-restore.md):

```bash
docker compose run --rm ops backup.sh        # archivio completo: dump + .env (+ config.yaml se override locale)
docker compose run --rm ops export.sh        # dump SQL leggibile, per ispezione/migrazione
docker compose run --rm ops restore.sh /backups/watchemall-backup-<data>.tar.gz
```

Il dump copre **anche tutte le configurazioni** (config DB-first). Cadenza consigliata: settimanale, quotidiana se lo storico è prezioso (un cron dell'host che invoca `backup.sh` è sufficiente).

## Aggiornamenti e plugin

- **Aggiornare il sistema**: nuova versione in `.env` (`WEA_VERSION`) → `docker compose pull && docker compose up -d`. Niente sorgenti, niente build.
- **Il set di plugin è quello dell'immagine** (tutti i first-party, vedi sopra): la governance è runtime — sospensione degli scraper dallo scheduler, interruttore globale dei notifier (PCFG-R8). Un set diverso richiede la build da sorgenti ([build-system](build-system.md)).

## Provare un'immagine di sviluppo

Oltre alle release puoi installare un'immagine **dev** per provare un branch **prima del merge** ([ci](ci.md#immagini-dev-su-pr)): basta puntare `WEA_VERSION` al tag dev del branch.

```bash
# nel .env
WEA_VERSION=dev-<branch>     # es. dev-catalog
docker compose pull && docker compose up -d
```

`dev-<branch>` è **sovrascritto** a ogni push sul branch (punti sempre all'ultima build). Per inchiodare una build esatta usa il **digest** (`image: ghcr.io/<owner>/watch-em-all@sha256:…`). Le immagini `dev-*` sono effimere: per l'uso normale resta su una release `x.y.z`.
