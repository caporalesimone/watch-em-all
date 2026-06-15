# CI

> **Infrastructure** · Audience: DevOps, developer.
>
> English mirror of [`docs/infrastructure/ci.md`](../../docs/infrastructure/ci.md), limited to what is implemented (DOC-12). The pipeline is born minimal in phase 0 and **grows with the flow**: linters and typecheck arrive with the first code (phase 1), contract and integration tests at scale (phase 12). Only the jobs that exist today are described here.

## Jobs (phase 0)

| Job | What it does | Gate |
|---|---|---|
| Build images | builds `watch-em-all` (app) and `watch-em-all-ops`; **on PRs** pushes them as `dev-<branch>` (see *Dev images*) | blocking |
| CHANGELOG guard | the PR must update `CHANGELOG.md` (one PR = one version, INF-19) | blocking |

Policy: `main` is always green; PRs are not merged with red jobs. Process details in [developer-rules](../../docs/developer-rules/README.md).

## Dev images (on PRs)

To **try the container before merge**, the build job pushes the images to GHCR with the tag **`dev-<branch>`** (sanitized branch name) on every PR open/update (drafts included), **overwritten** on each push: it always points at the latest build of that branch. Several branches in flight → distinct tags, no collision.

- **Branch without a PR**: manual trigger (`workflow_dispatch` with the branch as input) to produce `dev-<branch>` on demand.
- **No per-commit tags**: to pin an exact build use the **digest** (`@sha256:…`), always available.
- The `dev-*` images are **ephemeral**: the `dev-<branch>` tag is **deleted automatically when the PR closes** — merge or abandon — by the `cleanup-dev-images.yml` workflow (it also removes the orphan untagged manifest left behind), so the packages do not fill up with dead tags. Only release tags `x.y.z` are permanent (never touched by the cleanup).

How to install a dev image to try it: [deployment](deployment.md#trying-a-dev-image).

## Publish (on tag)

A separate workflow, triggered by **`x.y.z` tags** (plain SemVer, no `v` prefix; INF-17): it builds the two multi-stage images and pushes them to **GHCR**, then cuts the GitHub release with the **deploy kit** attached.

| Step | What it does |
|---|---|
| Build & push | `watch-em-all` (app: web+worker roles) and `watch-em-all-ops` → `ghcr.io/<owner>/…:<tag>` (e.g. `1.2.0`; never `latest`, INF-1) |
| Release + kit | attaches `compose.yml` (the release compose) and `.env.example` to the release — the **only two files** needed to install ([deployment](deployment.md)) |

The tag is the only publish trigger: a green `main` publishes nothing — and the tag is created **by the owner by hand**, when a release is wanted (see *Tags and releases* below). The GHCR **packages are public** (like the repo): the user-side pull is anonymous, no authentication.

### Product versioning

The product follows **SemVer** (`MAJOR.MINOR.PATCH`) with a **single version for the whole bundle** (core + first-party plugins, shipped together in the images); it is rule INF-19.

- `0.x` during development; **every PR** carries a version bump + a `CHANGELOG.md` entry (**1 MVP = 1 PR = 1 version**), but **tags are not per-PR**: the owner creates them by hand when a release is wanted, so the repo does not fill up with tags.
- `CHANGELOG.md` is updated in the **same PR** (the CI CHANGELOG guard enforces it).

### Tags and releases (manual)

The `x.y.z` tag (plain SemVer, **no `v` prefix**) is created **by the owner by hand**, when it is time for a release: **no auto-tag workflow**. Pushing the tag to GitHub triggers `publish.yml` (build+push of the versioned images to GHCR + a release with the deploy kit attached). Implemented in phase 0 (0.T9).

- Tags are **not per-PR**: the owner creates them **whenever wanted**; the intermediate (per-PR) versions live only in the CHANGELOG, untagged.
- The tag version is the latest `CHANGELOG.md` entry to publish; it can raise MINOR/MAJOR when the milestone warrants it.

## Notes

- No automatic deploy to installations: the CI **publishes** the images, updating stays the user's choice (`WEA_VERSION` in `.env` + `pull`), consistent with the self-hosted posture.
