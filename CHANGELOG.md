# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Every PR carries exactly one version bump and one entry here (1 MVP = 1 PR = 1 version). Release tags are **not** per-PR: the owner creates a plain SemVer `x.y.z` tag (no `v` prefix) **by hand** when a release is wanted, and pushing it triggers the publish workflow (versioned images + GitHub release); intermediate per-PR versions live only in this file.

## [0.0.12] - 2026-06-16

### Changed

- Healthchecks now use **curl everywhere** (dev + release compose): `curl` is installed in the app image (`packages/app/Dockerfile`, minimal — no recommends, apt lists wiped) and the `web` healthcheck switches from the Python stdlib probe to `curl -fsS http://localhost:8080/api/health`. One healthcheck command across dev and release — the previous python-in-dev / curl-in-release split is gone
- Worker heartbeat file now lives on a **`tmpfs`** (`/tmp` in RAM) in both composes: the per-tick write (CRON-R7 liveness) stays in memory and never reaches the disk. Cadence unchanged (60s tick, 180s stale threshold)

## [0.0.11] - 2026-06-16

### Fixed

- Dev-image cleanup now also removes the **orphan untagged manifest** left after unlinking a `dev-<branch>` tag (`delete-untagged: true`): previously each closed PR left behind a phantom `sha256:…` untagged version in GHCR, so the package filled up anyway. Release tags are never touched; safe because the images are single-arch

## [0.0.10] - 2026-06-16

### Fixed

- Dev-image cleanup no longer fails a PR close when the branch tag is the package's **only** version: GitHub forbids deleting the last tagged version of a package, so the cleanup step is now tolerant (`continue-on-error`). It's a transient case — it disappears once a release tag (`x.y.z`) is a permanent second version, after which dev-tag deletion always succeeds

## [0.0.9] - 2026-06-16

### Added

- Auto-cleanup of dev images (`.github/workflows/cleanup-dev-images.yml`): when a PR closes (merged or abandoned), the branch's `dev-<branch>` tag is deleted from the `watch-em-all` and `watch-em-all-ops` packages so GHCR does not fill up with stale dev tags. Only that tag is removed — release tags (`x.y.z`) are never touched. Uses the Actions `GITHUB_TOKEN` (falls back to a classic PAT with `delete:packages` if GitHub refuses to delete user-owned package versions)

### Changed

- Bump GitHub Actions to their Node 24 runtimes (Node 20 is deprecated): `actions/checkout` v4→v5, `docker/setup-buildx-action` v3→v4, `docker/login-action` v3→v4, `docker/build-push-action` v6→v7 in CI and publish

## [0.0.8] - 2026-06-15

### Changed

- Ship `web` and `worker` as a single image **`watch-em-all`** instead of two (`-web`/`-worker`): they share one codebase, one `pyproject`/lock and the same plugins — one application with two roles selected by the command (`web` | `worker`) via an entrypoint dispatcher. Published images drop from three to two (`watch-em-all` + `watch-em-all-ops`). `packages/web` + `packages/worker` merged into `packages/app`; both composes run web/worker from the same image via `command:`; CI and publish matrices updated (3 → 2); docs realigned (build-system, deployment, ci, developer-rules INF-17, phase-00)

### Fixed

- Disable buildx provenance attestations on push (`provenance: false` in CI and publish) — GHCR no longer shows a phantom `unknown/unknown` os/arch entry alongside each image

## [0.0.7] - 2026-06-15

### Added

- Base CI on PRs (`.github/workflows/ci.yml`, 0.T6): a CHANGELOG guard (PR fails if `CHANGELOG.md` is not updated — one PR = one version, INF-19) and a matrix job that builds the `web`/`worker`/`ops` images from the repo root. Linters/typecheck/tests come with the first code (1.T1)
- Dev images on PR (0.T7): the CI build job now pushes `web`/`worker`/`ops` to GHCR as `dev-<branch>` (branch slug, overwritten on each push) so a branch can be tried before merge; `workflow_dispatch` builds them on demand for branches without a PR (ci.md)
- Publish on tag + deploy kit (`.github/workflows/publish.yml`, 0.T9): an `x.y.z` tag (plain SemVer, no `v` prefix) — created by the owner by hand whenever a release is wanted — builds and pushes the three versioned images to GHCR and cuts the GitHub release with the deploy kit attached. Adds the kit files: `deploy/compose.yml` (release compose, image-based) and root `.env.example` (`WEA_VERSION` + `POSTGRES_*` + `ADMIN_INITIAL_PASSWORD`). Tagging is manual — there is no auto-tag workflow

## [0.0.6] - 2026-06-15

### Added

- Development compose (`docker-compose.yml`, 0.T5): the build-from-sources counterpart of the release deploy kit — `db` + `web` + `worker`, with `adminer` under profile `dev` (`:8081`) and the ephemeral `ops` under profile `ops`. Healthcheck on every long-running service and `json-file` log rotation everywhere (INF-2). Dev defaults on the DB env (`watchemall`) so `docker compose up` works without a `.env`; override via a local `.env`. The `web` stub healthcheck probes with the Python stdlib (the slim image ships no `curl`) — the release compose keeps `curl` for the real image (0.T9)

## [0.0.5] - 2026-06-13

### Removed

- GitHub CLI from the dev container (Dockerfile block + auth volume): git/GitHub operations (commit, push, PR) happen from the **host** by decision — the dev container only builds and runs. `gh` is installed on the host instead (declared exception to zero-install). Docs aligned (dev-container.md text + diagram, phase-00 0.T2)

## [0.0.4] - 2026-06-13

### Added

- Stub `worker` container (0.T4): heartbeat loop touching the file the compose healthcheck watches — declared mock, replaced by the real dispatcher/runner in 4.B1
- Stub `ops` container (0.T4): `postgres:16` + placeholder `ops/backup.sh`, `ops/export.sh`, `ops/restore.sh` (clear "not implemented yet" message, exit 1) — real scripts arrive with 1.T2/1.T3 and bake into the same image unchanged

## [0.0.3] - 2026-06-13

### Added

- Stub `web` container (0.T3): `packages/web/` multi-stage Dockerfile + stdlib placeholder server — "coming soon" page and `GET /api/health` always 200 (declared mock, replaced by the real app in 1.B2)
- Root `.dockerignore` (images build from the repo root)
- Dev-container architecture diagram in `docs/infrastructure/dev-container.md`

### Changed

- Tagging model (supersedes per-PR tags): versions still bump on every PR in the CHANGELOG, but release tags are created automatically only when a development-flow phase closes — 13 phases → 13 tags. Docs aligned (INF-19, ci, process rules); the auto-tag workflow lands as MVP 0.T8.

## [0.0.2] - 2026-06-13

### Added

- Dev container (`.devcontainer/`): Python 3.12 + Poetry, Node 22 + npm, git, Docker CLI + Compose plugin, GitHub CLI (0.T2)
- docker-outside-of-docker socket mount; named volume so `gh` auth survives container rebuilds; tolerant post-create that activates by itself once the toolchain files land (1.B1, 1.F1)
- `.gitattributes` forcing LF on `*.sh` (scripts run inside Linux containers; a CRLF checkout on Windows must never reach them)

## [0.0.1] - 2026-06-13

### Added

- Monorepo folder skeleton (`src/`, `packages/`, `ops/`, `deploy/`) as designed in `docs/infrastructure/build-system.md` (0.T1)
- `CHANGELOG.md` and the README operations-manual stub sections
- Project-specific `.gitignore` entries (frontend, backup archives, generated files) and root-anchored `lib/` so SvelteKit's `src/lib` is not ignored
