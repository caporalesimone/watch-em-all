# Environment variables

> **Infrastructure reference** · Audience: DevOps, developers.

Every environment variable **managed by Watch 'Em All** is prefixed **`WEA_`**. Variables consumed by
third-party images or libraries (PostgreSQL, libc, pgweb) keep the names those tools expect and are
listed separately at the bottom — they are *not* WEA-prefixed on purpose.

Configuration lives in a single `.env` file (copied from [`.env.example`](../.env.example)), read by
both composes. Bootstrap values are interpolated into [`config.yaml`](../config.yaml) by the app loader
at startup ([configuration](../../docs-ita/infrastructure/configuration.md)); secrets and a few
container vars come straight from the environment.

## WEA_ variables (managed by the app)

| Variable | Used by | Default | Purpose |
|---|---|---|---|
| `WEA_VERSION` | `compose.yml` (release) | — | Image tag to pull, e.g. `0.4.0` or `dev-<branch>`. **Selects which image to run; it is NOT the displayed product version** (that is baked from the git tag — see below). Ignored by `compose-dev.yml`, which builds. |
| `WEA_SECRET_KEY` | web, worker | — | HS256 signing key for the JWTs (AUTH-R3, ≥256 bit). Interpolated into `config.yaml` → `core.secret_key`. Generate with `openssl rand -hex 32`. |
| `WEA_ADMIN_INITIAL_USERNAME` | web (bootstrap) | `admin` | Username of the admin created on first boot. |
| `WEA_ADMIN_INITIAL_PASSWORD` | web (bootstrap) | _(unset → no bootstrap)_ | Temporary password of the initial admin; a change is forced at first login (AUTH-R8). If unset and there are no users, the bootstrap is skipped with a warning. |
| `WEA_SCHEMA_DRIFT_ALERT` | web | _unset → **off**_ | Dev safety net (4.B0). The startup schema-drift check **always runs and logs warnings**; this flag only controls whether `GET /api/health` **exposes** the drift (and thus whether the red dev banner shows). `.env`/`.env.example` ship it `true`. |
| `WEA_PORT` | web (entrypoint) | `8080` | Port uvicorn binds for the `web` role. |
| `WEA_STATIC_DIR` | web | `/app/static` | Directory of the built SPA served by FastAPI (absent in dev/tests → no SPA mount). Set in the image. |
| `WEA_CONFIG_FILE` | web, worker | `/app/config.yaml` | Path to the bootstrap `config.yaml`. |
| `WEA_VERSION_FILE` | web, worker | `/app/VERSION` | Path to the version file baked at build (see below). |
| `WEA_HEARTBEAT_FILE` | worker | `/tmp/worker-heartbeat` | Heartbeat file the worker touches each tick; watched by the compose healthcheck. (Stub today; real worker in 4.B1.) |
| `WEA_TICK_SECONDS` | worker | `60` | Worker tick interval, seconds. (Stub today.) |

## The product version (read this before bumping)

The **displayed** version (`GET /api/health.version`) is **not** set by any env var. It is the **git
tag**, cooked at build: the [Dockerfile](../packages/app/Dockerfile) runs `git describe --tags --always`
into `/app/VERSION`, which the config loader reads. So:

- **To make WEA report `0.4.x`** there must be a **git tag** `0.4.x` at the built commit. In a release,
  the maintainer creates and pushes the tag → the publish workflow builds the images baked with that
  version → the GitHub release is cut on the tag.
- `WEA_VERSION` (in `.env`) only tells the **release** `compose.yml` **which published image to pull** —
  set it to the same `x.y.z` as the tag.
- In **dev** (`compose-dev.yml` builds from source) the value is `git describe` of your HEAD, e.g.
  `0.3.4-7-g2c16a78`, until you create a local tag `0.4.0`.
- `pyproject.toml` / `package.json` versions are **inert `0.0.0` placeholders** — never bumped.
- `CHANGELOG.md` carries the human `[x.y.z]` entry; one tag per phase, no `v` prefix.

## External variables (not WEA-prefixed, on purpose)

| Variable | Consumed by | Notes |
|---|---|---|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | `postgres:16` image | Also interpolated into `config.yaml`'s `database_url` and into the dev `pgweb` `DATABASE_URL`. The Postgres image expects these exact names. |
| `TZ` | libc / Postgres | Installation timezone; entered times are interpreted here, stored timestamps stay UTC (BE-13). |
| `DATABASE_URL` | `pgweb` (dev only) | Built from `POSTGRES_*` in `compose-dev.yml` so pgweb opens straight on the database. The pgweb image expects this name. |
| `PGHOST` | `ops` scripts (libpq) | Defaults to `db` inside the ops container. |
