# Watch 'Em All — documentation (English, growing)

This is the project's **English documentation**, the destined canonical wiki. It **grows phase by phase**, translated from the Italian reference [`../docs-ita/`](../docs-ita/README.md), and currently covers only what has actually been **implemented**. The Italian `docs-ita/` stays the **source of truth during the transition**; when this English `docs/` is complete (closure of Phase 12 — Polish/v1), `docs-ita/` is retired.

## How it grows (DOC-12)

- At the **end of each development phase** ([development flow](../docs-ita/development-flow/README.md), process rule 8), the parts of `docs-ita/` covered by that phase are translated/adapted here, **and nothing more**.
- Same structure as `docs-ita/`: layers `1-business/` … `4-capabilities/`, plus the cross-cutting sections (`api/`, `infrastructure/`, …) as they become relevant.
- This documentation describes the **system as it exists**, never the system as it is planned: if a feature is not implemented yet, it does not appear here.
- Updating this folder is part of the **Definition of Done** of every phase — it grows in lockstep with the product.

## Contents

- **[infrastructure/](infrastructure/)** — the pipeline and process delivered in Phase 0:
  - [build-system.md](infrastructure/build-system.md) — monorepo layout and the two-image build
  - [dev-container.md](infrastructure/dev-container.md) — zero-install development environment
  - [ci.md](infrastructure/ci.md) — CI, dev images, publish on tag, versioning
  - [deployment.md](infrastructure/deployment.md) — pull-based deploy and the deploy kit

The business/architecture/feature layers arrive with the closure of Phase 1 — Foundations.
