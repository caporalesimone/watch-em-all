# Deployment (Docker)

> **Infrastruttura** · Audience: DevOps, system engineer. Snippet di configurazione ammessi (deroga dichiarata alle regole di layer).

## Servizi

| Servizio | Ruolo | Esposizione |
|---|---|---|
| `db` | PostgreSQL 16, unico stato del sistema | solo rete interna |
| `web` | FastAPI + bundle SPA; API, auth, scrape on-demand | `:8080` |
| `worker` | Dispatcher + pool scraper, alert, summary | nessuna |
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

## Backup

L'unico dato non ricostruibile è il DB (in particolare lo **storico prezzi**). Backup consigliato, a cura dell'host:

```bash
docker compose exec db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > backup-$(date +%F).sql.gz
```

In cron settimanale (o quotidiano se lo storico è prezioso). In alternativa: snapshot del volume `pgdata` a stack fermo.

## Aggiornamenti e plugin

- Aggiornare il sistema: `git pull && docker compose build && docker compose up -d`.
- **Abilitare/disabilitare un plugin** (campo `enabled` del manifest) richiede **rebuild + restart** (il bundle frontend è cucinato a build time): stesso comando di cui sopra.
