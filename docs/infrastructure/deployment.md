# Deployment (Docker)

> **Infrastructure** · Audience: DevOps, system engineer. Config snippets allowed (declared layer-rule exception).
>
> This document is the **reference**; the end-user operations manual is the repo **`README.md`**, which by rule (INF-18) holds all the deploy and maintenance instructions with every available command and script, and is updated with every new command introduced.

## Host requirements

The portal is hosted on **Linux**: locally inside **WSL2** or on a **dedicated server**. The only prerequisite is **Docker Engine + the Compose plugin** — no development or runtime software is installed on the host (no Python, Node, psql: everything lives in containers, INF-15). Development follows the same principle through the [dev container](dev-container.md); the hosting images are multi-stage and self-contained (the frontend is built inside the `web` image, INF-5).

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

The repo and the GHCR packages are **public**: the `pull` is **anonymous**, no `docker login` needed. The published images (pinned by version; a release also publishes a moving `latest` tag as a convenience — 5.T1 — but **pinning `WEA_VERSION` stays the recommended default**; INF-1 "never `latest`" is about *upstream* images, not our own artifacts):

| Image | Content |
|---|---|
| `ghcr.io/<owner>/watch-em-all:<ver>` | the app: FastAPI + built SPA + all first-party plugins + dispatcher/runner. **One image, two roles** selected by the command: `web` (API + SPA) and `worker` (scheduler + maintenance) |
| `ghcr.io/<owner>/watch-em-all-ops:<ver>` | `postgres:16` + [backup/export/restore](backup-and-restore.md) scripts |

**`config.yaml`**: the default is **inside the image** — no local file is needed. To customise it, create a copy next to the compose and mount it over the image's one (`./config.yaml:/app/config.yaml:ro`, a ready commented line in the release compose): the mount wins, the image stays the fallback.

**Plugins**: the plugin set is fixed **at image build** (the frontend bundle is baked in); the published images include **all the enabled first-party plugins**, and fine control stays at runtime (scraper suspension, notifier global switch PCFG-R8). A custom set requires a build from sources (the developer path, [build-system](build-system.md)).

## Services

| Service | Role | Exposure |
|---|---|---|
| `db` | PostgreSQL 16, the system's only state | internal network only |
| `web` | FastAPI + SPA bundle; API, auth, on-demand scrape | `:8080` |
| `worker` | Dispatcher + serial scraper runner, alerts, summary, daily maintenance | none |
| `ops` | backup/export/restore scripts, **ephemeral** (`run --rm`, `ops` profile) | none |

The release kit ships **no DB browser** (production-shaped): inspect the database with `docker compose exec db psql -U $POSTGRES_USER $POSTGRES_DB` or the `ops` container. The pgweb browser lives only in `compose-dev.yml`.

`web` and `worker` are **two services from the same image** `watch-em-all` (the role is chosen by `command`); they communicate **only through the DB**, both wait for `db` to be healthy and ensure the schema at startup (idempotent: no need to order them relative to each other).

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
    # config.yaml default included in the image; to customise it:
    # volumes: ["./config.yaml:/app/config.yaml:ro"]
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
    # volumes: ["./config.yaml:/app/config.yaml:ro"]   # same as web, optional
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
      - ./backups:/backups               # archives destination
      - ./.env:/host/.env:ro             # included in the backup
      # - ./config.yaml:/host/config.yaml:ro   # if a local override exists, back it up too
    depends_on:
      db: { condition: service_healthy }

volumes:
  pgdata:
```

Notes: no `version` field (deprecated in Compose v2); images pinned via `WEA_VERSION` in `.env`; log rotation everywhere. The `${VAR}` interpolation **inside** `config.yaml` is done by the application loader at startup, not by Docker (which only interpolates the compose file). The repo also has the **development compose** (`compose-dev.yml`, with `build:` instead of `image:`): the developer path, used by the [dev container](dev-container.md) — the two files share the same shape.

## Startup

```bash
cp .env.example .env            # then fill in the values
docker compose up -d            # production (no DB browser; inspect via `compose exec db psql` or `ops`)
```

First startup: the schema is created, the initial admin is born with the `WEA_ADMIN_INITIAL_PASSWORD` password and a forced change at first login.

## Health and monitoring

- `GET /api/health` → 200 if the app is alive and the DB reachable (includes the worker heartbeat age for information), otherwise 503.
- The worker is watched by the **heartbeat file** (healthcheck above) and by the heartbeat line in the system log (admin page).

## Exposure to the Internet (optional)

The project's posture accepts **HTTP on the LAN** ([security posture](../2-architecture/security-posture.md)). If the installation is exposed to the Internet, put a reverse proxy with TLS in front; example with Caddy:

```
watchemall.example.com {
    reverse_proxy localhost:8080
}
```

## Backup, export and restore

Scripts versioned in `ops/` and **baked into the `ops` image**, run **by hand** as an ephemeral container — details, rules and archive contents in [backup-and-restore.md](backup-and-restore.md):

```bash
docker compose run --rm ops backup.sh        # full archive: dump + .env (+ config.yaml if a local override)
docker compose run --rm ops export.sh        # readable SQL dump, for inspection/migration
docker compose run --rm ops restore.sh /backups/watchemall-backup-<date>.tar.gz
```

The dump covers **all the configuration too** (DB-first config). Recommended cadence: weekly, daily if the history is precious (a host cron invoking `backup.sh` is enough).

## Updates and plugins

- **Update the system**: new version in `.env` (`WEA_VERSION`) → `docker compose pull && docker compose up -d`. No sources, no build; the `pgdata` volume and your `.env` are untouched.
- **The plugin set is the image's** (all the first-party ones, see above): governance is at runtime — scraper suspension from the scheduler, notifier global switch (PCFG-R8). A different set requires a build from sources ([build-system](build-system.md)).

## Trying a development image

Besides releases, you can install a **dev** image to try a branch **before merge** ([ci](ci.md#dev-images-on-prs)): point `WEA_VERSION` at the branch's dev tag.

```bash
# in .env
WEA_VERSION=dev-<branch>     # e.g. dev-catalog
docker compose pull && docker compose up -d
```

`dev-<branch>` is **overwritten** on every push to the branch (you always get the latest build). To pin an exact build use the **digest** (`image: ghcr.io/<owner>/watch-em-all@sha256:…`). The `dev-*` images are ephemeral: for normal use stay on a release `x.y.z`.
