# Developer Rules

> Binding rules for project contributors. The CI enforces the automatable ones ([ci](../infrastructure/ci.md)); the rest are enforced in review.

## Sections

| Section | Content |
|---|---|
| [backend/rules.md](backend/rules.md) | Python: style, types, Pydantic, errors, logging, tests |
| [frontend/rules.md](frontend/rules.md) | Svelte/TypeScript: style, stores, API layer, design system, i18n |
| [infrastructure/rules.md](infrastructure/rules.md) | Docker, configuration, secrets, dependencies |
| [plugins/rules.md](plugins/rules.md) | Extra rules for plugin code |
| [documentation/rules.md](documentation/rules.md) | The 4-layer rules and wiki maintenance |

## Process rules (apply to everyone)

1. **`main` always green**: no merge with a red CI. Work on a branch, merge via PR even when working alone (the PR is where the diff and the CI live).
2. **Commits**: imperative, specific messages; one logical change per commit. Cite the requirement IDs when implementing (`feat: catch-up cross-midnight (CRON-R2)`).
3. **Requirements before code**: a new feature is written in the documents first (the right layer, a requirement ID), then in the code. If the code contradicts the wiki, one of the two is broken: fix them together in the same PR.
4. **API-first**: a new endpoint is born in [api/endpoints.md](../api/endpoints.md) before its implementation.
5. **No anonymous TODOs**: every `TODO` in the code has a reference (an issue or a documented open point).
6. **Simplifications are declared**: this is a hobby project and shortcuts are allowed ([security posture](../2-architecture/security-posture.md)) — but always in writing, never implicit.
7. **English docs at the end of a phase**: at the close of each [development flow](../../docs-ita/development-flow/README.md) phase, the English documentation in `docs/` (the designated canonical wiki) is updated with the equivalent of the implemented part only (DOC-12) — it grows with the site; `docs-ita/` stays the reference until `docs/` is complete (v1), then it is retired.
8. **Zero-install**: no development, dev or hosting software on the host — only Docker; development happens in the [dev container](../infrastructure/dev-container.md) (INF-15).
9. **One PR = one version; releases are tagged by the owner by hand**: every PR carries a **version bump** (SemVer) and a `CHANGELOG.md` entry; without them it is not mergeable (INF-19). Tags are **not** per-PR: the `x.y.z` tag (plain SemVer, no `v` prefix) is created **by the owner by hand** when a release is wanted ([ci](../infrastructure/ci.md#tags-and-releases-manual)) and pushing the tag publishes the images and the release; intermediate versions live only in the CHANGELOG.
10. **Owner merges**: the author of the change opens the PR (branch + commit + PR); **review and merge on `main` belong to the owner**. During a PR a dev image `dev-<branch>` is available to try before merge.
