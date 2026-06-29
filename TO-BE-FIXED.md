# TO BE FIXED

Running list of issues / polish noted by Simone, to address in a future pass.
New items get appended over time.

## Open

- **Generalize the shared UI pieces into a core-provided "SDK".** The category breadcrumb, the image
  element, and the **product cell** (the table-cell block with the linkable title + brand + category)
  are re-implemented in both the Catalog and the Dragon Store page. They should become ready-made
  components shipped by the core (a small SDK) so every page/plugin gets the same look from a single
  implementation. This is a concrete instance of the **shared plugin design-system** already gated for
  discussion before the notifier work: list these three widgets (category breadcrumb, image, product
  cell) as candidates in the
  [phase-7 "discuss before you start" gate](docs-ita/development-flow/phase-07-email-notifier.md) plus
  rule [FE-18](docs-ita/developer-rules/frontend/rules.md).

## Off topic

- **Two Claude Code skills: start-of-work and end-of-work.** Create a `/start-work` skill that opens a
  phase/PR (branch, dated status header, empty CHANGELOG placeholder, version bookkeeping) and an
  `/end-work` skill that closes it (finalize the CHANGELOG entry, tick the checklist, the tag +
  GitHub-release steps, image/version sanity check). They'd encode the repeatable versioning/tagging
  ritual — one tag per phase, no `v` prefix, `WEA_VERSION` in `.env`, version baked from `git describe`
  — so it isn't re-derived by hand each time. See [`docs/env-variables.md`](docs/env-variables.md) and
  the version notes in [ci](docs-ita/infrastructure/ci.md) for what the skills should automate.
