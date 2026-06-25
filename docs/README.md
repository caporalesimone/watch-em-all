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
- **[api/](api/)** — HTTP API (Phase 1: Auth, Me, Health):
  - [README.md](api/README.md) — conventions and Swagger
  - [endpoints.md](api/endpoints.md) — the implemented endpoints
- **[4-capabilities/](4-capabilities/)** — implemented capabilities:
  - [core/auth.md](4-capabilities/core/auth.md) — JWT auth, refresh rotation, forced/normal password change, bootstrap (Phase 1)
  - [database/schema.md](4-capabilities/database/schema.md) — the `users` table (Phase 1)
  - [frontend/app-shell.md](4-capabilities/frontend/app-shell.md) — SPA shell, theme, i18n, pages (Phase 1)
  - [frontend/auth-manager.md](4-capabilities/frontend/auth-manager.md) — the token manager (single-flight refresh) (Phase 1)
  - [core/plugin-registry.md](4-capabilities/core/plugin-registry.md) — discovery, validation, isolated loading (Phase 2)
  - [core/plugin-context.md](4-capabilities/core/plugin-context.md) — the minimal context handed to a plugin (Phase 2)
  - [frontend/plugin-discovery.md](4-capabilities/frontend/plugin-discovery.md) — generated registry + dynamic routing (Phase 2)

**Plugin system (Phase 2)** — the dynamic backbone:

- [2-architecture/plugin-architecture.md](2-architecture/plugin-architecture.md) — plugin-first, dynamic integration, isolation
- [3-features/plugins/dynamic-integration.md](3-features/plugins/dynamic-integration.md) — feature view: discovery, where plugins appear, lifecycle
- [plugin-development/manifest-reference.md](plugin-development/manifest-reference.md) — the `manifest.json` contract
- and the `core/`, `frontend/` capabilities listed above, plus [api/endpoints.md](api/endpoints.md) (plugin discovery) and [infrastructure/build-system.md](infrastructure/build-system.md) (unified frontend build)

**Phase 3 — Catalog & first scrape** — real scraping into a per-user catalog (0.3.0 → 0.3.4):

- [3-features/admin/user-management.md](3-features/admin/user-management.md) — create + list accounts, the role-split shell (0.3.0); plus the `/api/admin/users` endpoints in [api/endpoints.md](api/endpoints.md)
- [4-capabilities/contracts/product.md](4-capabilities/contracts/product.md) — the `Product` contract every scraper produces (brand, tags, category, prices, identity)
- [4-capabilities/core/catalog-update-service.md](4-capabilities/core/catalog-update-service.md) — the single write path: delta, history, delisting
- [3-features/plugins/scraper-plugin.md](3-features/plugins/scraper-plugin.md) — the scraper contract: stateless per-user producer, identity, tags/category, scrape-now cooldown
- [3-features/user/catalog-and-product-picker.md](3-features/user/catalog-and-product-picker.md) — the read-only catalog table (search, sort, paginate)
- [implemented-plugins/dragon-store/overview.md](implemented-plugins/dragon-store/overview.md) — the first scraper: real `.gp` product scraping (+ [features](implemented-plugins/dragon-store/features.md), [capabilities](implemented-plugins/dragon-store/capabilities.md))
- [4-capabilities/core/plugin-context.md](4-capabilities/core/plugin-context.md) gained `update_catalog` + a v0 `http` client (politeness, timeout, retries)

The remaining business/architecture/feature layers arrive as the corresponding features land in later phases.

---

- **[future-improvements/](future-improvements/)** — forward-looking **ideas to revisit after 1.0** (ideas, not todos; not tied to any phase).
