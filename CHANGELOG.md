# Changelog

All notable changes to this project are documented in this file.

The project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Every PR carries exactly one version bump and one entry here (1 MVP = 1 PR = 1 version). Release tags are **not** per-PR: the owner creates a plain SemVer `x.y.z` tag (no `v` prefix) **by hand** when a release is wanted, and pushing it triggers the publish workflow (versioned images on GHCR); the GitHub release is then created on that tag (no assets — the deploy kit lives in the repo). Intermediate per-PR versions live only in this file.

Each entry is **short** and reads as a user-facing story: first a **bullet list of what changed for you** (additions, removals and changes together, light on jargon), then a brief **_under the hood_** paragraph on the architectural/technical changes. Older entries predate this style and are left as they are.

## [0.4.0] - Unreleased

**Phase 4 — automatic scheduled scraping (the worker), plus the dev/admin tooling around it.**

### New

- **Scheduled scraping.** Set per-scraper daily times; the worker runs each scraper automatically, **one at a time**, catching up the last missed slot after downtime. (Slot-editor UI is next.)
- **Scrape cache.** Repeated page reads within a half-life come from a cache instead of the shop — fewer visits; an admin can clear a scraper's cache.
- **System log.** Worker/scraper events are recorded and readable by the admin (`GET /api/admin/logs`); old logs and runs auto-prune after `log_retention_days` (price history never does).
- **Feature flags page.** A self-building **Feature flags** page (dev knob: worker tick — non-persistent).
- **Scrapers & Notifiers admin.** Two admin areas list the loaded plugins by kind (icon + version): **Scrapers** also shows each scraper's schedule and opens its config page — politeness delay, HTTP timeout, cache half-life and the manual scrape-now cooldown — with a **Clear cache** button (changes apply on the next run, no restart); **Notifiers** lists the notifier plugins. (Replaces the earlier single Plugins list.)
- **Schema-drift safety net** (dev): a missing table/column surfaces in an **admin-only** banner/feed (`GET /api/admin/errors`), never on the public `/api/health`.

### Changed

- **Dev DB browser: Adminer → pgweb** — opens straight on the DB (no login); the **release** kit now carries **no** DB browser at all.
- **Heads-up — env vars renamed:** every variable is now **`WEA_`**-prefixed (e.g. `SECRET_KEY` → `WEA_SECRET_KEY`). Update your `.env`; see [`docs/env-variables.md`](docs/env-variables.md).

_Under the hood:_ a real `worker` (`src/worker`) ticks (interval from the `worker_tick` feature flag, re-read each second) and dispatches due slots to a **serial runner** under a per-scraper advisory lock shared with scrape-now (409 on overlap), with a run timeout from `system_settings` and `scrape_run`/`scrape_user_log` records. The scrape cache (`scrape_cache`, CTX-R9) and the system log (`system_log`) each sit behind a small **swappable interface** (`scrape_cache.py`, `system_log.py`) — Postgres today, a Redis backend later would be a localized swap; the worker drops expired cache at run start and prunes logs/runs past `log_retention_days` daily (price history never). Feature flags live in a `feature_flags` table shared by web and worker and cleared at web startup. Per-scraper operational settings live in `scraper_admin_config` (the core reserved keys), read by `build_context` for every run and scrape-now and superseding the former hard-coded constants and the `scrape_now_cooldown` dev flag. Schema drift iterates `Base.metadata` plus each plugin's declared `table_metadata` (DB-R7, enforced at load); pgweb is dev-only (no Compose profile, INF-3); env vars carry the `WEA_` prefix and the product version is baked from the git tag.

## [0.3.4] - 2026-06-25

**Phase 3 — consolidation: close the open items and round off the documentation.**

- After the **forced first-login password change** you're now **signed in automatically** and taken straight to your home — no second trip through the login page.
- **Dragon Store** plugin:
  - bumped to **0.2.0**, marking the move from the initial mock to real `.gp` product scraping.

_Under the hood:_ the English wiki (`docs/`) gains the phase-3 canonical pages, translated from `docs-ita/` and limited to what is implemented (DOC-12): the `Product` contract, the Catalog Update Service, the scraper-plugin contract, the Catalog & Product Picker, and the Dragon Store plugin (overview / features / capabilities).

## [0.3.3] - 2026-06-23

**Phase 3 — real Dragon Store scraping, with a catalog that shows the real product.**

- **Scrape now** and the dry-run preview read the real product page: title, price, list price, availability, image, **brand** and **category**.
- Products carry their **brand** (a link to the shop when available), a **category** breadcrumb (each step clickable), and **tags** like _Edizione Limitata_, _Offerta Raven Prime_ or _Pre Order_ — shown in the Catalog, the watched list and the dry-run preview.
- Marketing/edition labels are stripped from the product name and shown as tags instead, so titles stay clean.
- Pre-order items ("Prossimamente") count as orderable and are tagged _Pre Order_; out-of-stock items are marked unavailable.
- **Watched products** now appear like the preview — image, title, brand, category and a tags column — with the product **title resolved as soon as you add it** (not just the URL).
- Adding a product **already watched** is rejected with a clear message.
- **Catalog** page: the photo enlarges on hover (after a short pause, so it doesn't pop up while you scroll past), the product photo/title link to the shop (the separate "Open" column is gone), the **source** links to its scraper page, the **tags** sit in their own column, and you can sort by source, list price and availability too. The **discount** shows as a `-NN%` badge **under the price** (no separate Discount column), and the list price is struck through only when there's an actual discount. It also fills in on its own right after a scrape — no need to hit Search, and the empty page no longer flickers while it retries.
- Each scraper shows its **icon** next to the title and in the menu.

_Under the hood:_ a new stdlib `context.http` client gives every scraper politeness, a timeout, an identifiable user-agent, a request counter and short retries with backoff (no new dependency). The Dragon Store parser reads the page's JSON-LD `Product` (primary, unambiguous) for most fields and the JSON-LD `BreadcrumbList` for the category, taking the list price from the detail table and decoding windows-1252 + HTML entities while ignoring the page's many related products. `Product` gains `brand` (text + optional link), `tags` (a generic tag list) and `category` (a breadcrumb of `{text, link}`); the base scraper supplies the `add_tag`/`get_tags` and `add_child`/`get_path` mechanisms (the `tags` field/column is the renamed, generic former "product properties"). The Catalog's dormant `discount_pct` sort option was dropped (the discount has no column to sort). The title sanitizer is Dragon-Store-specific (hand-maintained label list). The watched list is backed by a product snapshot stored on the watch (set on add, refreshed each run). Plugin icons are auto-detected at load (`plugin-icon.ico` → `.svg`). Plugin frontends live outside the SvelteKit root, so they're registered as Tailwind sources (`@source` in `app.css`) to ensure plugin-only utility classes ship in the built CSS. Verified offline against saved real-page fixtures.

## [0.3.2] - 2026-06-20

**Phase 3 — watch a Dragon Store product and find it in your catalog.**

- Watch a Dragon Store product by pasting its URL on the scraper's page.
- Preview what a scrape would find, without saving anything (dry-run).
- **Scrape now** pulls your watched products into the catalog on demand.
- Right after a scrape, **Scrape now** rests for a while — the button shows a countdown until it's available again.
- New **Catalog** page: your products in a searchable, sortable, paginated table — price, discount, availability, source, and a link to the shop.
- Tidied the shell: the empty top bar is gone, and the light/dark theme toggle now lives in **Profile → Settings**.

_Under the hood:_ the first scraper drives the catalog end-to-end with **mock** data — real product identity (from the site's native id), invented prices — so the whole flow works before the real parser arrives. Scrapers write only through the catalog service; the manual scrape is rate-limited per scraper by a cooldown (a constant for now, admin-configurable in phase 4). Product identity is a shared template-method, so a product keeps the same id across runs. Spec reworked accordingly (SCR-R15), plus an English future-improvements page; `tp_scraper` stays as a throwaway test plugin.

## [0.3.1] - 2026-06-19

**Phase 3 — groundwork for the catalog (nothing visible yet).**

- No user-facing change: this lays the foundations the catalog and scrapers build on.

_Under the hood:_ adds the `Product` contract every scraper produces and the catalog tables (`products` + an append-only `price_history`, per-user, identity `user_id + plugin_id + external_id`). The Catalog Update Service is the **single write path**: it fills in missing prices, classifies each change (new / updated / price change / delisted), records history only when price or availability changes, and delists products missing from a delivery — a reappearing one comes back. `GET /api/catalog` reads the user's catalog (paginated, sortable, filterable). Backend only, verified by unit/API tests.

## [0.3.0] - 2026-06-19

**Phase 3 — admins can create the accounts that use the app.**

- Admins create user accounts (username, name, role, a temporary password) and see them in a list.
- A new account must change its temporary password at first login.
- The app splits by role: admins get an admin area, regular users get their own — no mixing.
- No self-registration: only an admin creates accounts.

_Under the hood:_ `POST`/`GET /api/admin/users` (admin-only; duplicate username → 409), the forced first-login password change, and a role-based shell with a route guard (plugin discovery loads only for users). User management was pulled forward from phase 10 so a `user` account can exist before the catalog. Deferred to phase 10: reset password, disable/enable, soft-delete with grace + restore, status filters, last-login sort, courtesy notifications, the load dashboard.

## [0.2.0] - 2026-06-18

**Phase 2 — Plugin system.** Opened with post-0.1.0 polish; the plugin-system backbone is below.

### Fixed

- **Worker stops promptly on `docker stop`.** The stub worker runs as PID 1, which ignores signals that have no handler, so Docker waited the full ~10s stop timeout before SIGKILL. It now installs a SIGTERM/SIGINT handler and exits cleanly (verified: ~0.3s).

### Added

- **Plugin system — the dynamic backbone (phase 2).** Plugins are auto-discovered full-stack folders under `src/plugins/{scrapers,notifiers}/<name>/`, each described by a declarative `manifest.json`.
  - *Backend:* a manifest parser with validation (type ↔ folder, `api_version`, snake_case `name`, kebab `route_base`); a registry that loads the enabled plugins with **per-plugin failure isolation** (a broken plugin is rejected and logged — the app and the other plugins stay up); a minimal **Plugin Context** (own DB engine/session for `plugin_<name>_*` tables, namespaced logger, empty admin config — the logger/config are declared phase-2 stubs until `system_log` and the ConfigField infra land); `GET /api/plugins` discovery (no internal paths); each plugin mounts its router under `/api{route_base}` with a `Plugin: <name>` Swagger tag; icons served from `/api/plugin-assets/{name}/icon`.
  - *Frontend:* a `build:plugins` step generates the component registry from the manifests (gitignored, never hand-edited); a single catch-all route `plugins/[...rest]` mounts plugin pages dynamically; scrapers appear in a collapsible **SCRAPERS** sidebar group, notifiers never do; bundle/runtime mismatches are surfaced in the console, never as a broken page. Plugins import only via `$lib` (so they resolve from outside the SvelteKit root); the `$plugins` alias + Vite `fs.allow` let the single Vite build bundle them.
  - Ships two throwaway **Test Plugins** — TP Scraper (full-stack) and TP Notifier (backend-only) — that exercise the whole path; they will be removed when real plugins land.
- **Product version on the login page** too (small line under the form), fetched from `GET /api/health` — alongside the version already shown in the sidebar.
- **`docs/updates/phase-02.md`**: the phase-2 companion doc, including the browser command to preview the Italian translation (`localStorage.setItem('wea_lang','it')` + reload).
- **Autofocus** on the new-password field when the forced password-change page opens (verified: the focused element is `input[name=new-password]`).

### Changed

- **Dev and release stacks no longer share a database volume.** Distinct Compose project names — `compose-dev.yml` → `watch-em-all-dev`, `compose.yml` → `watch-em-all` — so each gets its own named volume regardless of the folder it runs from. `compose.yml` also documents (commented) how to switch the DB to a local bind mount if preferred.
- **Every functional API now sits behind authentication.** Only `/api/health`, `/api/auth/login`, `/api/auth/refresh` and the static plugin icon (`/api/plugin-assets/...`, loaded by the browser as an `<img>`) stay public; the plugin discovery and every plugin route now require a logged-in user. Each endpoint also carries a one-line English `summary` shown in Swagger.
- **Sidebar:** the brand is now "👀 Watch 'Em All"; the version line is a centered link that opens Swagger (`/api/docs`) in a new tab (same text, no other restyle).
- Removed obsolete `.gitkeep` placeholders now that `src/{core,web,frontend}` and the plugin folders carry real content (kept `src/worker/.gitkeep`, still empty until phase 4).

## [0.1.0] - 2026-06-17

**Phase 1 — Foundations.** The live skeleton: the real application, authentication and the SPA shell replace the phase-0 stubs. (Developed as a single batch on `main`; this entry consolidates the whole phase.)

### Added

- **Backend (FastAPI).** Config loader (1.B1): `config.yaml` + `.env` with `${VAR}` / `${VAR:-default}` interpolation, fail-fast validation, reads the baked product version. `GET /api/health` (1.B2): DB check + product version, Swagger at `/api/docs`, `{detail, code}` error envelope (BE-11). Users + initial-admin bootstrap (1.B3): `users` table with bcrypt hashing and **first/last name**, admin created from the environment with a forced password change. JWT auth (1.B4–1.B6): login/logout, refresh with `jti` rotation and reuse → 401 + global logout, `token_version` invalidation, the `must_change_password` gate (via an `mcp` access claim, no DB read), `account_disabled`, in-memory login rate limit. Profile (1.B7): `GET/PATCH /api/me` (id, username, first/last name, role, locale).
- **Frontend (SvelteKit 2 / Svelte 5 SPA, 1.F1–1.F5).** Scaffold + svelte-i18n (`en` complete fallback + `it`) + dark/light theme with no flash; Auth Manager (access in memory, refresh in localStorage, single-flight + proactive refresh); login → route guard → protected shell (sidebar + header); forced first password change (no current password) and the normal change (current required), both with a hidden username field for password managers; dashboard greeting by first name; profile showing Username / Name / Surname / Role; the product version shown small under *Log out*. The `web` image builds and serves the SPA (`spa.py`, client-side-routing fallback).
- **Version source of truth (1.T4).** The git tag: computed at build via `git describe` and baked into the image (`/app/VERSION`), exposed on `/api/health`; `pyproject.toml`/`package.json` keep an inert placeholder. A `publish.yml` guard verifies the tag matches the top CHANGELOG entry (the CHANGELOG is verified, not the source).
- **CI (1.T1).** `backend-checks` (ruff, `ruff format --check`, `mypy --strict`, pytest) and `frontend-checks` (`prettier --check`, `svelte-check`, build) on every PR.
- **Ops scripts (1.T2/1.T3).** Real `backup.sh` / `export.sh` / `restore.sh` (custom + plain dumps; restore verifies the archive, refuses while the app is connected, recreates the DB), replacing the phase-0 placeholders.
- Dev affordance: a `wea_lang` localStorage override to preview the Italian translation (no selector exposed in V1).

### Changed

- **Documentation pivots to English.** `docs/` becomes the English canonical wiki (grows phase by phase; the implemented phase-1 capabilities are written there), `docs-ita/` is the Italian source of truth during the transition (retired at v1). New `docs/updates/` holds per-phase, feature-level summaries with *Good to know* and *Useful Commands* (not linked from the wiki).
- **Single configuration source; composes at the repo root.** Both composes read `.env` (`env_file`), with no inline defaults — `.env.example` is the single source. `compose.yml` (the default) is the release/image compose; `compose-dev.yml` builds from sources; the `deploy/` folder is removed.
- `GET /api/me` is exempt from the must-change-password gate (it drives the SPA boot and carries the user's name).

### Fixed

- Frontend polish: svelte-i18n initialised at module load (no "set the initial locale" error); a page `<title>`; form `name` attributes; missing assets return a clean 404 instead of the SPA HTML; `replaceState` guard redirects; no throwaway `GET /api/me` 401 on reload (proactive refresh on boot).

## [0.0.17] - 2026-06-16

### Changed

- README **Releasing** section now spells out the correct order — **tag → build → release**: push the tag from the CLI, wait for the publish workflow to go green, then create the GitHub release on the *existing* tag. Publishing a release from the UI with a *new* tag would announce the version before its images are built (a window where `docker compose pull` fails). The deploy kit stays in the repo

### Docs

- **Phase 0 closed** (`phase-00-pipeline.md` → ✅, 0.T10 and the remaining DoD boxes ticked; flow index updated): the end-to-end pull-based cycle was exercised on `0.0.16` (tag → images on GHCR → release → clean install fetching the kit from the repo: `pull` + `up` → all healthy, `/api/health` 200)

## [0.0.16] - 2026-06-16

### Changed

- Deploy kit is **no longer attached as a release asset**: `deploy/compose.yml` and `.env.example` live in the repo and users fetch them at the release tag (raw URLs in the README install). This sidesteps GitHub's immutable releases entirely (no assets to freeze, no leading-dot asset-name issue) — a release can now be created freely from the **GitHub UI or the CLI**. The publish workflow's `release` job is **removed**: on a tag it only builds and pushes the two versioned images (`permissions` narrowed to `contents: read`). Supersedes the draft-staging approach from 0.0.15
- Docs realigned to "kit in the repo, not attached": README (Installation + Releasing), `deployment.md`, `ci.md` (IT + `docs-eng` mirror), `build-system.md` (IT + mirror), `INF-17`/`INF-19`, `phase-00`/`phase-12`

## [0.0.15] - 2026-06-16

### Changed

- Publish workflow is now **immutable-releases-safe** (GitHub made immutable releases the default: a published release's assets are frozen). The release job no longer creates a published release and then uploads the kit (which fails with `422 Cannot upload assets to an immutable release`). Instead it **stages a draft release with the deploy kit attached** and stops; the owner reviews, writes the notes and publishes it from the UI — at which point the release becomes immutable *with* the kit. The tag must be pushed from the CLI (drafts don't trigger workflows). Supersedes the idempotent-upload approach from 0.0.14
- Added a guardrail: if a **published** release already exists for the tag (released by hand from the UI), the job flips it to pre-release (best-effort, to avoid poisoning `/releases/latest`) and fails with clear instructions — a hand-published release can't receive the kit and that version is permanently reserved

### Added

- README **Releasing (maintainer)** section: a reminder of the manual release procedure (CLI tag → workflow stages the draft with the kit → publish from the UI) and the warning never to publish a release by hand from the UI

### Docs

- `ci.md` (IT + `docs-eng` mirror): the *tag and releases* section describes the new draft-staging procedure and the immutable-release caveat

## [0.0.14] - 2026-06-16

### Changed

- Publish workflow release step is now **idempotent**: if the release for the tag already exists (e.g. the tag was created by publishing a release from the GitHub UI), it only (re)attaches the deploy kit with `--clobber` instead of failing on `gh release create`. A tag pushed from the CLI still creates the release as before — so the owner can tag/release from the GitHub UI **or** the CLI. Docs aligned (ci.md); fixed a stale "three images" comment in the workflow header (it builds two)

## [0.0.13] - 2026-06-16

### Added

- README operations manual (0.T10, INF-18): the phase-0 operational sections — **Installation (pull-based)**, **Updating**, **Trying a dev image** — are filled with the real, tested commands (download the deploy kit, set `WEA_VERSION`, `docker compose pull && up -d`)
- English documentation (`docs-eng/infrastructure/`, DOC-12): English mirror of the four infrastructure docs implemented in phase 0 — `build-system`, `dev-container`, `ci`, `deployment` — describing only what exists (stub containers, the two-image build, CI/publish/cleanup, the pull-based deploy). `docs-eng` index updated accordingly

### Fixed

- Development compose: the `worker` service now **builds** the shared `watch-em-all:dev` image (via a YAML anchor on the `web` build) instead of only referencing it — a plain `docker compose up --build` no longer fails with `pull access denied` for the worker. The image is built once; the second build is a cache hit. Surfaced by the 0.T10 end-to-end dry run

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
