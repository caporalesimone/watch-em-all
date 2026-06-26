# CI

> **Infrastructure** · Audience: DevOps, developer.
>
> English translation of the Italian reference [`docs-ita/infrastructure/ci.md`](../../docs-ita/infrastructure/ci.md), limited to what is implemented (DOC-12). The pipeline is born minimal in phase 0 and **grows with the flow**: linters and typecheck arrive with the first code (phase 1), contract and integration tests at scale (phase 12). Only the jobs that exist today are described here.

## Jobs

| Job | What it does | Gate |
|---|---|---|
| Backend lint | `ruff check .` · `ruff format --check .` | blocking |
| Backend typecheck | `mypy` (strict) | blocking |
| Backend tests | `pytest` (unit + contract; integration on a Postgres service) | blocking |
| Frontend lint | `prettier --check` · `svelte-check` | blocking |
| i18n consistency | `i18n:check` — English keys **used vs defined** (core + plugins); 4.B11. Also runs **before the build** (`prebuild`) and **on tag** (job `i18n-guard`, a prerequisite of *Build images*) | blocking |
| Frontend build | `npm run build` (runs `build:plugins` + `i18n:check`) | blocking |
| Build images | builds `watch-em-all` (app) and `watch-em-all-ops`; **on PRs** pushes them as `dev-<branch>` (see *Dev images*) | blocking |
| CHANGELOG guard | the PR must update `CHANGELOG.md` (one PR = one version, INF-19) | blocking |

Policy: `main` is always green; PRs are not merged with red jobs. Process details in [developer-rules](../../docs-ita/developer-rules/README.md).

### Backend tests — layout and commands

`tests/` **mirrors `src/`**: one subpackage per subsystem, so a test for `src/<area>/foo.py` lives in `tests/<area>/`. `conftest.py` (shared fixtures, e.g. `client`) and the root `__init__.py` apply to every subfolder.

| Folder | What it holds |
|---|---|
| `tests/core/` | domain/service logic (`src/core/*`): catalog, cache, settings, schedule, locks, system log, security, … |
| `tests/web/` | endpoints/API via `TestClient` (`src/web/routers/*`) |
| `tests/worker/` | dispatcher and serial runner (`src/worker/*`) |
| `tests/plugins/` | plugin framework (manifest, registry, discovery, context, scraper identity) |
| `tests/plugins/dragon_store/` | the Dragon Store plugin + its `fixtures/` (saved real pages) |

```bash
poetry run pytest                                                          # whole suite (recursive)
poetry run pytest tests/web                                                # one group
poetry run pytest tests/plugins/dragon_store/test_dragon_store_parser.py   # one file
```

## Dev images (on PRs)

To **try the container before merge**, the build job pushes the images to GHCR with the tag **`dev-<branch>`** (sanitized branch name) on every PR open/update (drafts included), **overwritten** on each push: it always points at the latest build of that branch. Several branches in flight → distinct tags, no collision.

- **Branch without a PR**: manual trigger (`workflow_dispatch` with the branch as input) to produce `dev-<branch>` on demand.
- **No per-commit tags**: to pin an exact build use the **digest** (`@sha256:…`), always available.
- The `dev-*` images are **ephemeral**: the `dev-<branch>` tag is **deleted automatically when the PR closes** — merge or abandon — by the `cleanup-dev-images.yml` workflow (it also removes the orphan untagged manifest left behind), so the packages do not fill up with dead tags. Only release tags `x.y.z` are permanent (never touched by the cleanup).

How to install a dev image to try it: [deployment](deployment.md#trying-a-dev-image).

## Publish (on tag)

A separate workflow, triggered by **`x.y.z` tags** (plain SemVer, no `v` prefix; INF-17): it builds the **two** multi-stage images and pushes them to **GHCR**. The **GitHub release** (with its notes) is created by the **owner** (UI or CLI); the **deploy kit is not attached** to the release — it lives in the repo and is fetched from there ([deployment](deployment.md)).

| Step | What it does |
|---|---|
| Build & push | `watch-em-all` (app: web+worker roles) and `watch-em-all-ops` → `ghcr.io/<owner>/…:<tag>` (e.g. `1.2.0`; never `latest`, INF-1) |

The tag is the only publish trigger: a green `main` publishes nothing — and the tag is created **by the owner by hand**, when a release is wanted (see *Tags and releases* below). The GHCR **packages are public** (like the repo): the user-side pull is anonymous, no authentication.

### Product versioning

The product follows **SemVer** (`MAJOR.MINOR.PATCH`) with a **single version for the whole bundle** (core + first-party plugins, shipped together in the images); it is rule INF-19.

- `0.x` during development; **every PR** carries a version bump + a `CHANGELOG.md` entry (**1 MVP = 1 PR = 1 version**), but **tags are not per-PR**: the owner creates them by hand when a release is wanted, so the repo does not fill up with tags.
- `CHANGELOG.md` is updated in the **same PR** (the CI CHANGELOG guard enforces it).

### Single source of truth for the version

The product version has **one source of truth: the git tag**. It is not written by hand in any versioned file — `pyproject.toml` and `package.json` keep an **inert placeholder** `version` (we do not publish PyPI/npm packages): the real version is **computed at build** from `git describe --tags --always` and **baked into the image** (`/app/VERSION` file). So:

- **on a tag** (release): `git describe` returns the bare tag → `x.y.z`;
- **off a tag** (dev, branch, local build): `x.y.z-N-g<sha>` ("N commits past release `x.y.z`, at commit `<sha>`") — every build shows a **real, reconstructible version**, never a placeholder like `0.0.0`.

The app **exposes** this version at runtime: `GET /api/health` reports it (and so do the Swagger title and the UI footer). One formula, computed in one place (the Dockerfile), identical for release, dev and local builds.

The **`CHANGELOG.md` is not the source: it is only verified.** A guard in `publish.yml` checks, on tag push, that the tag matches the version of the **top entry** of `CHANGELOG.md`; on a mismatch the publish fails (preventing the "I tagged before finalizing the changelog" drift). `WEA_VERSION` in `.env` is yet another thing: it is the **operator's choice** of which image to run (the tag to `pull`), not the product version.

> Build notes: `git describe` needs the git history in the context — `.git/` is included in the build context (not in `.dockerignore`) and the workflows use `fetch-depth: 0` (the default checkout is shallow and without tags). `git` is installed only in the **build stage** (multi-stage): the final image carries only the version string, not `.git`. `--dirty` is intentionally omitted: the build context is a filtered copy of the tree (it excludes tracked dirs like `docs/`), so a working-tree dirty flag would be meaningless — `describe` reads `.git` refs only, no working tree needed.

### Tags and releases (manual)

The `x.y.z` tag (plain SemVer, **no `v` prefix**) is created **by the owner by hand**, when it is time for a release: **no auto-tag workflow**. Pushing the tag to GitHub triggers `publish.yml` (build+push of the versioned images to GHCR). Implemented in phase 0 (0.T9).

- Tags are **not per-PR**: the owner creates them **whenever wanted**; the intermediate (per-PR) versions live only in the CHANGELOG, untagged.
- **Release procedure**: the owner creates the tag **from the GitHub UI** (by publishing a release with its notes) **or from the CLI** (`git tag x.y.z && git push origin x.y.z`); pushing the tag triggers `publish.yml`, which builds and pushes the versioned images. The **deploy kit is not attached to the release** — it lives in the repo and the user fetches it at the release tag ([deployment](deployment.md)). With no release assets, GitHub's *immutable releases* impose nothing: a release can be created freely from the UI.
- The tag version is the latest `CHANGELOG.md` entry to publish; it can raise MINOR/MAJOR when the milestone warrants it. **`publish.yml` verifies** the tag matches that entry and fails on drift (see *Single source of truth for the version*).

## Notes

- No automatic deploy to installations: the CI **publishes** the images, updating stays the user's choice (`WEA_VERSION` in `.env` + `pull`), consistent with the self-hosted posture.
