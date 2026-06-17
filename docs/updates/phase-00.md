# Phase 0 — Pipeline & infrastructure

> Feature-level recap. Not user-facing: phase 0 builds the rails the product runs on.

## What's implemented

- **Zero-install dev container**: the whole toolchain (Python, Node, Docker CLI) lives in a dev container; nothing is installed on the host except Docker. Git/GitHub stays on the host.
- **Two Docker images**, built and published to GHCR:
  - `watch-em-all` — the app, with two roles (`web` | `worker`) chosen by the start command.
  - `watch-em-all-ops` — `postgres:16` + the backup/export/restore scripts.
- **CI on every PR**: a CHANGELOG guard + a build of both images, pushed to GHCR as `dev-<branch>` so a branch can be tried before merge. Dev tags are auto-cleaned when the PR closes.
- **Publish on tag**: pushing an `x.y.z` tag builds and pushes the versioned images. The **deploy kit** (`deploy/compose.yml` + `.env.example`) lives in the repo and is fetched at the tag — not attached to the release.
- **Pull-based install**: the operator never downloads sources — just the deploy kit, then `docker compose pull && up`.
- In phase 0 the app containers are **stubs** (a "coming soon" page + a heartbeat worker); they get replaced by the real app in phase 1.

## Good to know

- Nothing to "use" yet — this phase is exercised by deploying and seeing healthy containers and a placeholder page.
- The released images are public on GHCR (anonymous pull).

## Useful Commands

Docker runs inside **WSL** (Ubuntu) on this machine. From a Windows shell you can drive it via `wsl.exe`; the repo is mounted at `/mnt/d/#Simone/watch-em-all`.

```bash
# open a WSL shell in the repo
wsl.exe -d Ubuntu-24.04 -e bash -lc "cd '/mnt/d/#Simone/watch-em-all' && exec bash"

# build + start the dev stack (from inside the repo in WSL)
docker compose up -d --build

# check the two images built
docker images | grep watch-em-all

# stop / reset
docker compose down            # stop
docker compose down -v         # stop + wipe the database volume
```
