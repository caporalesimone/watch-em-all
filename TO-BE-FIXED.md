# TO BE FIXED

Running list of issues / polish noted by Simone, to address in a future pass.
New items get appended over time.

## Open

- **Catalog — extra space in the category breadcrumb.** In the Catalog the categories print as
  `cat1 / cat2 / cat3` with an unwanted space around the `/`, because
  [`catalog/+page.svelte`](src/frontend/src/routes/catalog/+page.svelte#L262-L278) lays each segment on
  its own indented line and HTML collapses the newlines into a rendered space. The Dragon Store plugin
  page renders the same breadcrumb but packs the markup with no inter-element whitespace
  ([`PluginRoot.svelte`](src/plugins/scrapers/dragon_store/frontend/PluginRoot.svelte#L334-L340)) and
  looks better — `Giochi di Ruolo/GDR Italiano/Il Richiamo di Cthulhu` beats
  `Giochi di Ruolo/ GDR Italiano/ Il Richiamo di Cthulhu`. Fix: render the catalog breadcrumb tight,
  the way Dragon Store does.

- **Generalize the shared UI pieces into a core-provided "SDK".** The category breadcrumb, the image
  element, and the **product cell** (the table-cell block with the linkable title + brand + category)
  are re-implemented in both the Catalog and the Dragon Store page — and the spacing bug above is
  exactly what that duplication causes. They should become ready-made components shipped by the core
  (a small SDK) so every page/plugin gets the same look from a single implementation. This is a
  concrete instance of the **shared plugin design-system** already gated for discussion before the
  notifier work: list these three widgets (category breadcrumb, image, product cell) as candidates in
  the [phase-7 "discuss before you start" gate](docs-ita/development-flow/phase-07-email-notifier.md)
  plus rule [FE-18](docs-ita/developer-rules/frontend/rules.md).

- **Admin — a live log page, early.** It would help to have an admin web page to read the system logs
  **live** (and browse past ones) sooner rather than later — a single place to see what the system is
  doing. The full design already lives in phase 4: `4.B7` (`system_log` table + `GET /api/admin/logs?since=`
  cursor) and `4.F3`/`4.F4` (the polling page with filters, autoscroll, heartbeat). **Needs analysis**:
  decide whether to pull a *minimal* version forward — a simple page that shows recent log lines
  (present + past) — and, deliberately, **how much to show and how** (which sources/levels, a tail of
  N lines, plain polling vs cursor). Goal: a simple place to read logs now, improved later; the
  analysis decides if it belongs in phase 4 or stays as `4.F3/F4`.

- **Worker container exposes `8080/tcp` but serves nothing (cosmetic).** `docker ps` on the dev
  stack shows the `worker` container with `8080/tcp` exposed even though the worker serves no HTTP
  (it's the heartbeat stub today, the real dispatcher in 4.B1) — the port is just `EXPOSE 8080`
  metadata inherited from the shared `watch-em-all` image (one image, two roles `web`/`worker` by
  command, by design). It is **not published** (no host mapping) so it's harmless, only noisy in
  `docker ps`. Revisit with 4.B1: either accept/document it, or split the EXPOSE so only the `web`
  role advertises the port. Observed:
  ```
  7ab0f417bb56  watch-em-all:dev  …  Up (healthy)  8080/tcp                       …-worker-1
  26f3f3ce703f  watch-em-all:dev  …  Up (healthy)  0.0.0.0:8080->8080/tcp         …-web-1
  0f7c989370fe  sosedoff/pgweb…   …  Up            0.0.0.0:8081->8081/tcp         …-pgweb-1
  14eb07aee657  postgres:16       …  Up (healthy)  5432/tcp                       …-db-1
  ```

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
