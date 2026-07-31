# TODO

Running list of issues / polish noted by Simone, to address in a future pass.
New items get appended over time. **Done items are removed from here** — the record of what was
decided and why lives in the commits (`git log`), in the CHANGELOG entry of the version that
shipped it, and in the phase document.

> The **phase-9 code review** (groups A, B and C — 22 findings) was closed on 2026-07-31 and has
> been removed from this file. Its decisions are in `git log --grep='(C'` — one commit per item,
> each stating the fact that settled it — and summarised in the `[0.9.0]` CHANGELOG entry. Two of
> the answers grew past the review and became architecture: `build_product` in the scraper base
> (SCR-R18), and the price history re-keyed per product rather than per user (CATSVC-R4). Two
> halves were deliberately deferred with a reason: the automatic cleanup of delisted products and
> the notification that reports it to [phase 15](docs-ita/development-flow/phase-15-catalog-notifications.md),
> pruning history nobody references to [phase 16](docs-ita/development-flow/phase-16-history-custody.md).

## Off topic

- **Two Claude Code skills: start-of-work and end-of-work.** Create a `/start-work` skill that opens a
  phase/PR (branch, dated status header, empty CHANGELOG placeholder, version bookkeeping) and an
  `/end-work` skill that closes it (finalize the CHANGELOG entry, tick the checklist, the tag +
  GitHub-release steps, image/version sanity check). They'd encode the repeatable versioning/tagging
  ritual — one tag per phase, no `v` prefix, `WEA_VERSION` in `.env`, version baked from `git describe`
  — so it isn't re-derived by hand each time. See [`docs/env-variables.md`](docs/env-variables.md) and
  the version notes in [ci](docs-ita/infrastructure/ci.md) for what the skills should automate.
