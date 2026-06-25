# Deployment (Docker)

> **Infrastructure** · Audience: DevOps, system engineer. Config snippets allowed (declared layer-rule exception).
>
> English translation of the Italian reference [`docs-ita/infrastructure/deployment.md`](../../docs-ita/infrastructure/deployment.md), limited to what is implemented (DOC-12). This document is the **reference**; the end-user operations manual is the repo **`README.md`** (INF-18). In phase 0 the application containers are **stubs** — the deploy process is real, the served page is a placeholder.

## Host requirements

The portal is hosted on **Linux**: locally inside **WSL2** or on a **dedicated server**. The only prerequisite is **Docker Engine + the Compose plugin** — no development or runtime software is installed on the host (no Python, Node, psql: everything lives in containers, INF-15). The hosting images are multi-stage and self-contained (INF-5).

## Installation: pull, not build

The deploy is **pull-based** (INF-17): the CI publishes the images to GHCR on every tag ([ci](ci.md)) and the user **never downloads the sources** — only the **deploy kit**, two files kept **in the repo** (not attached to the release), fetched at the wanted release tag:

| File | Role |
|---|---|
| `compose.yml` | the release compose: references the published images, no `build:` |
| `.env.example` | secrets template + image version (`WEA_VERSION`) |

```bash
mkdir watchemall && cd watchemall
VERSION=0.0.16        # the release you want (a published tag)
curl -LO https://raw.githubusercontent.com/<owner>/watch-em-all/$VERSION/compose.yml
curl -LO https://raw.githubusercontent.com/<owner>/watch-em-all/$VERSION/.env.example
cp .env.example .env                  # then fill in the values (WEA_VERSION=$VERSION)
docker compose pull && docker compose up -d
```

The repo and the GHCR packages are **public**: the `pull` is **anonymous**, no `docker login` needed. The published images (pinned by version, never `latest` — INF-1):

| Image | Content |
|---|---|
| `ghcr.io/<owner>/watch-em-all:<ver>` | the app. **One image, two roles** selected by the command: `web` and `worker`. In phase 0: stub (placeholder page + heartbeat) |
| `ghcr.io/<owner>/watch-em-all-ops:<ver>` | `postgres:16` + backup/export/restore scripts (placeholders in phase 0, real in 1.T2/1.T3) |

## Services

| Service | Role | Exposure |
|---|---|---|
| `db` | PostgreSQL 16, the system's only state | internal network only |
| `web` | app role: serves the page and `GET /api/health` | `:8080` |
| `worker` | worker role: heartbeat loop (real scheduling in 4.B1) | none |
| `ops` | backup/export/restore scripts, **ephemeral** (`run --rm`, profile `ops`) | none |

The release kit ships **no DB browser** (production-shaped): inspect the database with `docker compose exec db psql -U $POSTGRES_USER $POSTGRES_DB` or the `ops` container. The pgweb browser lives only in `compose-dev.yml`.

`web` and `worker` are **two services from the same image** `watch-em-all` (the role is chosen by `command`); both wait for `db` to be healthy.

## compose.yml (release, the deploy-kit file)

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
    env_file: [.env]
    depends_on:
      db: { condition: service_healthy }
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:8080/api/health"]
      interval: 30s
      timeout: 5s
      retries: 3
    restart: unless-stopped
    logging: *logging

  worker:
    image: ghcr.io/<owner>/watch-em-all:${WEA_VERSION}
    command: ["worker"]
    env_file: [.env]
    tmpfs:
      - /tmp          # heartbeat in RAM: the per-tick write never hits the disk
    depends_on:
      db: { condition: service_healthy }
    healthcheck:
      # heartbeat: the worker touches this file every tick (CRON-R7)
      test: ["CMD-SHELL", "test $(($(date +%s) - $(stat -c %Y /tmp/worker-heartbeat))) -lt 180"]
      interval: 60s
      timeout: 5s
      retries: 3
    restart: unless-stopped
    logging: *logging

  ops:
    image: ghcr.io/<owner>/watch-em-all-ops:${WEA_VERSION}
    profiles: [ops]                      # never runs on its own: docker compose run --rm ops …
    env_file: [.env]
    volumes:
      - ./backups:/backups               # archive destination
    depends_on:
      db: { condition: service_healthy }

volumes:
  pgdata:
```

Notes: no `version` field (deprecated in Compose v2); images pinned via `WEA_VERSION` in `.env`; log rotation everywhere (INF-2). `curl` ships in the app image, so the same healthcheck is used by the development and release composes. The repo also has the **development compose** (`compose-dev.yml`, with `build:` instead of `image:`): the developer path used by the [dev container](dev-container.md) — the two files share the same shape.

## Updating

Change the version in `.env` (`WEA_VERSION`) → `docker compose pull && docker compose up -d`. No sources, no build; the `pgdata` volume and your `.env` are untouched.

## Trying a development image

Besides releases, you can install a **dev** image to try a branch **before merge** ([ci](ci.md#dev-images-on-prs)): point `WEA_VERSION` at the branch's dev tag.

```bash
# in .env
WEA_VERSION=dev-<branch>     # e.g. dev-catalog
docker compose pull && docker compose up -d
```

`dev-<branch>` is **overwritten** on every push to the branch (you always get the latest build) and exists **only while the PR is open** (it is deleted on close). To pin an exact build use the **digest** (`watch-em-all@sha256:…`). For normal use stay on a release `x.y.z`.
