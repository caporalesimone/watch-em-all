# Developer Rules — Infrastructure

> Binding for Docker, configuration and dependency management. Docs: [infrastructure/](../../infrastructure/deployment.md).

## Docker and compose

- **INF-1** — **Pinned** images (never `latest`): `postgres:16`, `sosedoff/pgweb:0.16.2`, base images with an explicit tag.
- **INF-2** — Log rotation on every application service (`max-size`/`max-file`); healthchecks on `db`, `web` (health endpoint) and `worker` (heartbeat file).
- **INF-3** — Debug tools (pgweb and the like) **live only in the development stack** (`compose-dev.yml`) and are **absent** from the default `compose.yml`: the separation between the two files is the gate (not a profile), and the default compose stays production-shaped.
- **INF-4** — Read-only mounts where possible (`config.yaml:ro`); no code bind-mounts in production.
- **INF-5** — Multi-stage Dockerfiles: the frontend build and the Poetry install are separate from the final stage; the final images carry no build toolchain.

## Configuration and secrets

- **INF-6** — Hierarchy respected: bootstrap in `config.yaml`, secrets in `.env`, everything else in the DB ([configuration](../../infrastructure/configuration.md)). Never new operational parameters in `config.yaml` "for convenience".
- **INF-7** — `.env` **never** committed; `.env.example` always up to date with every new key (same PR).
- **INF-8** — No secrets in logs, in API errors or in commit messages. Plugin secret fields stay write-only end to end.
- **INF-9** — Safe defaults: every new system setting is born with a prudent, documented default ([SystemSettings](../../4-capabilities/contracts/scheduling-models.md)).

## Dependencies

- **INF-10** — Backend: **a single `pyproject.toml` at the root** with **a single committed `poetry.lock`** (no per-package lockfile: web and worker share the environment and the plugins); new dependencies justified in the PR (prefer the standard library when reasonable — e.g. sending SMTP). Plugin dependencies in **optional groups** of the single pyproject, installed by the Dockerfiles that serve them.
- **INF-11** — Frontend: `package-lock.json` committed; no UI dependencies that duplicate the design system.
- **INF-12** — Dependency updates in dedicated PRs (not mixed with features).

## Host and environments

- **INF-15** — **Zero-install on the host**: the hosting target is **Linux** (WSL2 locally or a dedicated server) and the only prerequisite is Docker Engine + Compose. No development or runtime software is ever installed on the host — neither the development nor the hosting one: the toolchain lives **only in the containers** (development: [dev container](../../infrastructure/dev-container.md); hosting: self-contained multi-stage images, INF-5). A setup instruction that begins with "install X on the host" (X ≠ Docker) is a violation.
- **INF-17** — **Pull-based releases**: installation happens **without sources**. The publish workflow ([ci](../../infrastructure/ci.md)), triggered by the `x.y.z` tags (plain SemVer, no `v` prefix), publishes the two images — `watch-em-all` (app: `web` and `worker` roles) and `watch-em-all-ops` — to GHCR. The **deploy kit** (`compose.yml` + `.env.example`) **lives in the repo** (it is not attached to the release: the user downloads it at the version's tag): those **two files must always be enough** for a complete installation. Any change that introduces a new host file, mount or variable updates the deploy kit **in the same PR**. The default `config.yaml` lives in the images; the local override is an optional mount.
- **INF-18** — **The repo's `README.md` is the complete operations manual**: it contains (or links, in a single place) **all** the instructions to deploy and maintain the site — step-by-step pull-based installation, version upgrade, backup/export/restore with **all the available commands and scripts**, optional exposure to the Internet, basic troubleshooting (health, heartbeat, logs). Every new operational command or script is added to the README **in the same PR** that introduces it; a from-scratch installation must succeed reading only the README (verified at release, phase 12).
- **INF-19** — **Product versioning**: **SemVer** (`MAJOR.MINOR.PATCH`), **a single version for the bundle** (core + first-party plugins). **Every PR carries a version bump and a `CHANGELOG.md` entry** (without them it is not mergeable) — **1 MVP = 1 PR = 1 version**. **Tags are not per-PR**: the `x.y.z` tag (plain SemVer, **no `v` prefix**) is created **by the owner by hand** when a release is wanted, and pushing the tag builds the release images (the deploy kit lives in the repo, INF-17). **MAJOR** on a public-API break or a non-additive DB schema change (DB-R4). The preview **dev** images are tagged `dev-<branch>` (mutable, on PRs; see [ci](../../infrastructure/ci.md#dev-images-on-prs)). Distinct from the plugins' `api_version` (contract gate) and the manifest's informative `version`. **Version source of truth = the git tag**: no number hand-written in versioned files (`pyproject.toml`/`package.json` keep an inert placeholder `version`), the version is computed at build from `git describe` and baked into the image, exposed at `/api/health`; the `CHANGELOG.md` is **only verified** (`publish.yml` checks the tag matches the top entry). Detail: [ci](../../infrastructure/ci.md#single-source-of-truth-for-the-version).

## Data

- **INF-13** — Schema: additive with `CREATE ... IF NOT EXISTS`; breaking changes require a documented manual SQL script (DB-R4). Dropping & recreating the whole schema is **forbidden**: `price_history` is not reconstructible. (The only exception: restore from a backup, which *is* the state being brought back to life — [backup-and-restore](../../infrastructure/backup-and-restore.md).)
- **INF-14** — Any maintenance script that touches production data is written idempotent and tried first on a dump.
- **INF-16** — The **backup/export/restore** scripts (`ops/`, baked into the `ops` image, run manually with `docker compose run --rm ops …` — [backup-and-restore](../../infrastructure/backup-and-restore.md)) are updated **in the same PR** as any change that touches what they save (new config files, new volumes, format changes); `restore.sh` always asks for confirmation and verifies the archive before touching the DB.
