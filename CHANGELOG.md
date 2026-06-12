# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Every PR carries exactly one version bump and one entry here (1 MVP = 1 PR = 1 version). Release tags are **not** per-PR: a `vX.Y.Z` tag is created automatically when an entry contains the phase-closing marker `Closes phase N.` (13 phases → 13 tags).

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
