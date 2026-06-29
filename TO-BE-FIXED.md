# TO BE FIXED

Running list of issues / polish noted by Simone, to address in a future pass.
New items get appended over time.

## Open

- **Generalize the shared UI pieces into a core-provided "SDK".** The category breadcrumb, the image
  element, and the **product cell** (the table-cell block with the linkable title + brand + category)
  are re-implemented in both the Catalog and the Dragon Store page — and the spacing bug above is
  exactly what that duplication causes. They should become ready-made components shipped by the core
  (a small SDK) so every page/plugin gets the same look from a single implementation. This is a
  concrete instance of the **shared plugin design-system** already gated for discussion before the
  notifier work: list these three widgets (category breadcrumb, image, product cell) as candidates in
  the [phase-7 "discuss before you start" gate](docs-ita/development-flow/phase-07-email-notifier.md)
  plus rule [FE-18](docs-ita/developer-rules/frontend/rules.md).

- **Admin — a live log page (frontend only now).** `4.B7` shipped in `0.4.0`: the `system_log`
  table + the cursor API `GET /api/admin/logs` (no `since` → latest N; `since=<id>` → only newer rows;
  `level`/`source` filters; `limit` 1–1000). So the **backend is done** — what's left is just the UI,
  `4.F3`/`4.F4` (the polling page with filters, autoscroll). A *minimal* page is now a thin consumer of
  that endpoint: load the latest N, then poll with `since=<maxId>`. Decisions already taken: **no
  heartbeat log row** (the page's heartbeat/liveness cue must come from `/api/health` + the file
  heartbeat, not from a log line); the worker/scraper are the only sources persisted. Still open for
  `4.F3/F4`: polling cadence, sidebar placement, one page vs two (cursor page + filters page).

## Off topic

- **Two Claude Code skills: start-of-work and end-of-work.** Create a `/start-work` skill that opens a
  phase/PR (branch, dated status header, empty CHANGELOG placeholder, version bookkeeping) and an
  `/end-work` skill that closes it (finalize the CHANGELOG entry, tick the checklist, the tag +
  GitHub-release steps, image/version sanity check). They'd encode the repeatable versioning/tagging
  ritual — one tag per phase, no `v` prefix, `WEA_VERSION` in `.env`, version baked from `git describe`
  — so it isn't re-derived by hand each time. See [`docs/env-variables.md`](docs/env-variables.md) and
  the version notes in [ci](docs-ita/infrastructure/ci.md) for what the skills should automate.

## Done / moved

- The **shared plugin design-system** (Scrape-now-in-core + the common core-frontend widget set) is the
  [phase-7 "discuss before you start" gate](docs-ita/development-flow/phase-07-email-notifier.md) plus
  rule [FE-18](docs-ita/developer-rules/frontend/rules.md).
- The **Adminer → pgweb** swap (and the `dev`-profile decision — resolved as "no profile, dev-only")
  was done in 0.4.0 ([phase-4 `4.B0b`](docs-ita/development-flow/phase-04-worker-scheduling.md)).
- **Catalog — extra space in the category breadcrumb** — fixed in `0.5.0` (branch `feat/phase-5`,
  commit `341ab22`): the catalog breadcrumb markup is now packed tight with no inter-element
  whitespace, the way the Dragon Store page already rendered it.
- **Worker `8080/tcp` in `docker ps` — accepted, not fixed** (decided 2026-06-29). It is harmless
  image metadata: `EXPOSE 8080` is documentation only (it publishes nothing); the `worker` service has
  no `ports:` mapping and its healthcheck stats the heartbeat file, never touching 8080. The proposed
  "split the EXPOSE so only `web` advertises the port" is impossible by design — one shared image, the
  `web`/`worker` role is chosen at runtime by `command`, so a `EXPOSE` baked into that single image
  can't be made role-specific without re-forking into two images (reverting `0.0.8`). The only clean
  alternative (drop `EXPOSE 8080`, optionally re-declare `expose:` on the `web` compose service) is a
  lateral trade — it loses the web image's port self-documentation — so the cosmetic noise is accepted.
