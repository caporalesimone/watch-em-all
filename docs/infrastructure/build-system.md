# Build system and monorepo

> **Infrastructure** · Audience: DevOps, developer. Config snippets allowed.
>
> English translation of the Italian reference [`docs-ita/infrastructure/build-system.md`](../../docs-ita/infrastructure/build-system.md), limited to what is implemented (DOC-12). Phase 0 ships the repository skeleton and the image build, with **stub** application containers; the source tree under `src/` is still empty placeholders, filled phase by phase.

## Monorepo

```
watch-em-all/
├── .devcontainer/   # zero-install development environment (dev-container.md)
├── src/             # backend/frontend sources — placeholders in phase 0
│   ├── core/        # backend core modules
│   ├── web/         # FastAPI app (API + static SPA)
│   ├── worker/      # dispatcher + runner
│   ├── frontend/    # SvelteKit app
│   └── plugins/
│       ├── scrapers/<name>/    # manifest.json, backend/, frontend/
│       └── notifiers/<name>/
├── packages/
│   ├── app/         # Dockerfile + entrypoint of the app image (web|worker roles via command)
│   └── ops/         # Dockerfile of the ops image (postgres:16 + scripts)
├── ops/             # backup/export/restore scripts (backup-and-restore.md)
├── deploy/
│   └── compose.yml  # release compose (GHCR images): deploy kit in the repo, fetched at the tag
├── docs/            # English documentation — grows phase by phase (canonical at v1)
├── docs-ita/        # Italian documentation — source of truth during the transition
├── docker-compose.yml  # development compose (build: from sources)
├── CHANGELOG.md     # release history (SemVer, INF-19)
└── .env(.example)
```

The **published images** are **two** — `watch-em-all` (the app: `web` and `worker` roles) and `watch-em-all-ops` (`postgres:16` + scripts) — built and pushed to GHCR by the publish workflow on every tag ([ci](ci.md)); the end user installs with the deploy kit alone, no sources ([deployment](deployment.md), INF-17).

- **One app image for `web` and `worker`** (`packages/app/`): they share the same codebase and the same plugins — they are **one application with two roles**, not two components. The role is selected by the **start command** (`command: ["web"]` / `["worker"]`) through an entrypoint that dispatches; this way a **single artifact** is built and versioned instead of two near-identical ones. `ops` stays separate because it has a different base (`postgres:16`).
- The image build context is the **repository root**: `docker build -f packages/app/Dockerfile .`. The Dockerfiles are **multi-stage from day one** (INF-5) and self-contained.
- Stack (fixed at major versions on day one — new project, no migration debt): backend Python 3.12+, Poetry, FastAPI; frontend Node 22 LTS, SvelteKit 2. The build tooling (single root `pyproject.toml`, the unified Vite build, the plugin registry) lands with the first code (phase 1) and is documented here as it arrives.
- The product **version** has a single source of truth in the **git tag**: it is not hand-written in any versioned file (`pyproject.toml`/`package.json` keep an inert placeholder `version`), but computed at build from `git describe` and baked into the image, exposed on `/api/health` ([ci](ci.md#single-source-of-truth-for-the-version)).

## Phase 0 — stub containers

In phase 0 the application containers carry no product logic; they exist to exercise the whole pipeline end to end:

| Image / role | What it does in phase 0 | Replaced by |
|---|---|---|
| `watch-em-all` · `web` | static "coming soon" page + `GET /api/health` always 200 (stdlib server, `packages/app/stub/`) | 1.B2 (real FastAPI app) |
| `watch-em-all` · `worker` | heartbeat loop touching the file the healthcheck watches + a tick log | 4.B1 (real worker) |
| `watch-em-all-ops` | `postgres:16` + placeholder `backup.sh`/`export.sh`/`restore.sh` ("not implemented yet", exit 1) | 1.T2/1.T3 (real scripts) |
