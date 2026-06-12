# Deployment (Docker)

> **Infrastruttura** · Audience: DevOps, system engineer. Snippet di configurazione ammessi (deroga dichiarata alle regole di layer).

## Requisiti dell'host

Il portale è hostato su **Linux**: in locale dentro **WSL2** oppure su un **server dedicato**. L'unico prerequisito è **Docker Engine + Compose plugin** — sull'host non si installa alcun software di sviluppo o runtime (niente Python, Node, psql: tutto vive nei container, INF-15). Per lo sviluppo vale lo stesso principio tramite il [dev container](dev-container.md); le immagini di hosting sono multi-stage e autosufficienti (frontend buildato dentro l'immagine `web`, INF-5).

## Servizi

| Servizio | Ruolo | Esposizione |
|---|---|---|
| `db` | PostgreSQL 16, unico stato del sistema | solo rete interna |
| `web` | FastAPI + bundle SPA; API, auth, scrape on-demand | `:8080` |
| `worker` | Dispatcher + runner seriale scraper, alert, summary, manutenzione giornaliera | nessuna |
| `adminer` | Ispezione DB dal browser | `:8081`, **solo profilo `dev`** |

`web` e `worker` comunicano **solo tramite il DB**; entrambi attendono `db` healthy e garantiscono lo schema all'avvio (idempotente: non serve ordinarli tra loro).

## docker-compose.yml

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_USER: "${POSTGRES_USER}"
      POSTGRES_PASSWORD: "${POSTGRES_PASSWORD}"
      POSTGRES_DB: "${POSTGRES_DB}"
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./ops:/ops:ro                    # script di backup/export/restore (backup-and-restore.md)
      - ./backups:/backups               # destinazione archivi (gitignorata)
      - ./config.yaml:/host/config.yaml:ro
      - ./.env:/host/.env:ro
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
    build: { context: ., dockerfile: packages/web/Dockerfile }
    ports: ["8080:8080"]
    volumes: ["./config.yaml:/app/config.yaml:ro"]
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
    build: { context: ., dockerfile: packages/worker/Dockerfile }
    volumes: ["./config.yaml:/app/config.yaml:ro"]
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

Note: niente campo `version` (deprecato in Compose v2); immagini pinnate; log rotation ovunque; `config.yaml` montato read-only. L'interpolazione `${VAR}` **dentro** `config.yaml` è fatta dal loader applicativo all'avvio, non da Docker (che interpola solo il compose file).

## Avvio

```bash
cp .env.example .env            # poi compilare i valori
docker compose up -d            # produzione (senza adminer)
docker compose --profile dev up # sviluppo: + adminer su http://localhost:8081
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

Script versionati in `ops/`, montati nel container `db` ed eseguiti **a mano** — dettagli, regole e cosa contengono gli archivi in [backup-and-restore.md](backup-and-restore.md):

```bash
docker compose exec db /ops/backup.sh        # archivio completo: dump + config.yaml + .env
docker compose exec db /ops/export.sh        # dump SQL leggibile, per ispezione/migrazione
docker compose exec db /ops/restore.sh /backups/watchemall-backup-<data>.tar.gz
```

Il dump copre **anche tutte le configurazioni** (config DB-first). Cadenza consigliata: settimanale, quotidiana se lo storico è prezioso (un cron dell'host che invoca `backup.sh` è sufficiente).

## Aggiornamenti e plugin

- Aggiornare il sistema: `git pull && docker compose build && docker compose up -d`.
- **Abilitare/disabilitare un plugin** (campo `enabled` del manifest) richiede **rebuild + restart** (il bundle frontend è cucinato a build time): stesso comando di cui sopra.
