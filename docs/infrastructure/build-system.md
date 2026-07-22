# Build system and monorepo

> **Infrastructure** · Audience: DevOps, developer. Config snippets allowed.

## Monorepo

```
watch-em-all/
├── .devcontainer/   # zero-install development environment (dev-container.md)
├── src/
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
├── backups/         # archives produced by the scripts (gitignored)
├── docs/            # English documentation — grows phase by phase (canonical at v1)
├── docs-ita/        # Italian documentation — source of truth during the transition
├── compose.yml      # release compose (GHCR images): the deploy kit, fetched at the tag
├── compose-dev.yml  # development compose (build: from sources)
├── pyproject.toml   # SINGLE, at the root: backend dependencies + optional groups
├── poetry.lock      # a single lockfile for the whole backend
├── CHANGELOG.md     # release history (SemVer, INF-19)
├── config.yaml      # default, baked into the images; local override via mount
└── .env(.example)
```

The **published images** are **two** — `watch-em-all` (the app: `web` and `worker` roles) and `watch-em-all-ops` (`postgres:16` + scripts) — built and pushed to GHCR by the publish workflow on every tag ([ci](ci.md)); the end user installs with the deploy kit alone, no sources ([deployment](deployment.md), INF-17).

- **One app image for `web` and `worker`** (`packages/app/`): they share the same codebase, the same `pyproject.toml`/`poetry.lock` and the same plugins — they are **one application with two roles**, not two components. The role is selected by the **start command** (`command: ["web"]` / `["worker"]`), through an entrypoint that dispatches; this way a **single artifact** is built and versioned instead of two near-identical ones. `ops` stays separate because it has a different base (`postgres:16`).
- **A single root `pyproject.toml`** (a single `poetry.lock`): the backend dependencies are unique — a second lockfile would only create drift to keep aligned by hand. The app Dockerfile installs from the root, selecting the **optional groups** it needs. The `version` field of `pyproject.toml` (and `package.json`) is an **inert placeholder**: we do not publish packages, and the product version has a single source of truth in the **git tag**, computed at build from `git describe` and exposed at `/api/health` ([ci](ci.md#single-source-of-truth-for-the-version)).
- **Plugins are not formal packages**: they are folders auto-discovered by the registry. Their Python dependencies (e.g. a headless browser) are declared in the single root `pyproject.toml`, in a dedicated **optional group**.
- Backend stack: Python 3.12+, Poetry, FastAPI, SQLAlchemy, Pydantic v2.
- Frontend stack: **Node 22 LTS**, **SvelteKit 2** (Svelte 5, runes), **Tailwind CSS 4**, **svelte-i18n**, Vite. Major versions fixed on day 1 (a new project, no migration debt).

## Unified frontend build

A single Vite process includes the app and the enabled plugins:

```
npm run build
  ├── 1. build:plugins        # reads every manifest.json in src/plugins/**
  │       ├── keeps enabled=true with a frontend.entry
  │       └── generates src/frontend/src/generated/plugin-registry.ts
  └── 2. vite build           # SvelteKit (adapter-static, SPA fallback)
```

Rules:

- The generated registry is **never** hand-written (`FDISC-R1`).
- Adding a plugin = a folder with a valid manifest + a conforming `frontend/index.ts`: **zero** changes to build or routing.
- Plugins import the core components via `$lib/components` (single build: no cross-bundle issue).
- **Tailwind scans both `src/frontend` and `src/plugins`**: the plugin frontends live **outside** the SvelteKit root (which Tailwind 4 auto-discovers on its own), so they are registered explicitly as sources (`@source '../../plugins/**/*.{svelte,ts,js}'` in `app.css`) so that the utilities used **only** by the plugins end up in the built CSS.
- **Operational consequence**: changing `enabled` requires a rebuild of the `web` image (the bundle is baked into the Dockerfile: `RUN npm run build`) + restart. Also documented in [deployment](deployment.md).

## Backend tooling

```toml
[tool.ruff]
line-length = 100
lint.select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.mypy]
strict = true
```

The usage rules (what must pass before a merge) are in [developer-rules/backend](../developer-rules/backend/rules.md); the pipeline that runs them in [ci.md](ci.md).
