# Watch 'Em All — documentation (English, canonical)

This is the project's **English documentation** — the **canonical wiki**. It describes the
system **as it actually exists** (phases 0–5, implemented and released), organized by the
same four layers as the source spec plus the cross-cutting sections.

It **grows phase by phase**: at the close of each phase the newly-implemented slices are
translated/adapted here from the Italian reference [`../docs-ita/`](../docs-ita/README.md).
The Italian `docs-ita/` is no longer the full source of truth — it now holds only the
**spec-ahead** slices (phase 6+, not yet built), the [`development-flow/`](../docs-ita/development-flow/README.md)
roadmap and [`future-improvements/`](../docs-ita/future-improvements/README.md). It shrinks
each phase as content migrates here, and is retired at v1 (close of Phase 12 — Polish/v1).

## How it grows (DOC-12)

- At the **end of each development phase** ([development flow](../docs-ita/development-flow/README.md), process rule 8), the parts of `docs-ita/` covered by that phase are translated/adapted here, **and nothing more**.
- This documentation describes the **system as it exists**, never the system as it is planned: if a feature is not implemented yet, it does not appear here (it lives, spec-ahead, in `../docs-ita/`).
- Updating this folder is part of the **Definition of Done** of every phase — it grows in lockstep with the product.
- A few links below deliberately point into [`../docs-ita/`](../docs-ita/README.md): those are **spec-ahead** references (the roadmap, notification architecture) that have no implemented counterpart yet.

## Contents

### Layer 1 — Business (`1-business/`)
High-level product/audience view; text and at most a few Mermaid diagrams, no code.

- [product-overview.md](1-business/product-overview.md) — what Watch 'Em All is: problem, solution, core concepts, roles
- [use-cases.md](1-business/use-cases.md) — the concrete scenarios the product serves
- [personas-and-roles.md](1-business/personas-and-roles.md) — who uses it and the role split
- [user-experience.md](1-business/user-experience.md) — the end-user journey
- [admin-experience.md](1-business/admin-experience.md) — the administrator journey
- [glossary.md](1-business/glossary.md) — shared vocabulary

### Layer 2 — Architecture (`2-architecture/`)
System- and feature-level architecture; text + Mermaid, no code.

- [system-overview.md](2-architecture/system-overview.md) — the whole system at a glance (web, worker, DB, plugins)
- [data-and-multitenancy.md](2-architecture/data-and-multitenancy.md) — data model, per-user isolation, product identity, catalog lifecycle, config DB-first
- [security-posture.md](2-architecture/security-posture.md) — the deliberate simplifications and their rationale
- [plugin-architecture.md](2-architecture/plugin-architecture.md) — plugin-first, dynamic integration, soft-sandbox isolation
- [scheduling-and-execution.md](2-architecture/scheduling-and-execution.md) — the scraper dispatcher, catch-up, serial runner, run observability

### Layer 3 — Features (`3-features/`)
Detailed feature views (user / admin / plugin); text + Mermaid, no code.

- **admin/**
  - [plugin-configuration.md](3-features/admin/plugin-configuration.md) — configuring plugins at system level
  - [scraper-scheduling-and-limits.md](3-features/admin/scraper-scheduling-and-limits.md) — schedules, cooldowns and limits
  - [system-logs-and-maintenance.md](3-features/admin/system-logs-and-maintenance.md) — logs, health and maintenance
  - [user-management.md](3-features/admin/user-management.md) — create/list accounts, the role-split shell
- **plugins/**
  - [dynamic-integration.md](3-features/plugins/dynamic-integration.md) — discovery, where plugins appear, lifecycle
  - [scraper-plugin.md](3-features/plugins/scraper-plugin.md) — the scraper contract: stateless per-user producer, identity, tags/category, scrape-now cooldown
- **user/**
  - [carts.md](3-features/user/carts.md) — the two cart modes, membership rules, the € savings threshold (€ ↔ % mirror)
  - [catalog-and-product-picker.md](3-features/user/catalog-and-product-picker.md) — the read-only catalog table (search, sort, paginate) and the "add selected to a cart" picker
  - [price-history.md](3-features/user/price-history.md) — recorded price/availability history
  - [profile-and-notifiers.md](3-features/user/profile-and-notifiers.md) — user profile and notifier settings

### Layer 4 — Capabilities (`4-capabilities/`)
Technical capabilities, contracts and data schema; the only layer with pseudocode and code references.

- **contracts/**
  - [adjustment.md](4-capabilities/contracts/adjustment.md) — the `Adjustment` a scraper returns for a single-store cart
  - [product.md](4-capabilities/contracts/product.md) — the `Product` contract every scraper produces
  - [scheduling-models.md](4-capabilities/contracts/scheduling-models.md) — the scheduling data models
- **core/**
  - [auth.md](4-capabilities/core/auth.md) — JWT auth, refresh rotation, forced/normal password change, bootstrap
  - [cart-engine.md](4-capabilities/core/cart-engine.md) — the read-only engine: totals, adjustments, final estimate, threshold state, health flag
  - [catalog-update-service.md](4-capabilities/core/catalog-update-service.md) — the single write path: delta, history, delisting
  - [cron-worker.md](4-capabilities/core/cron-worker.md) — the worker that runs due scrapes
  - [plugin-context.md](4-capabilities/core/plugin-context.md) — the minimal context handed to a plugin (`engine`, `db`, `logger`, `config`, `update_catalog`, `http`)
  - [plugin-registry.md](4-capabilities/core/plugin-registry.md) — discovery, validation, isolated loading
  - [price-history.md](4-capabilities/core/price-history.md) — how price/availability history is recorded and read
  - [scraper-pool.md](4-capabilities/core/scraper-pool.md) — the pool that executes scraper plugins
- **database/**
  - [schema.md](4-capabilities/database/schema.md) — the released tables (users, products, price_history, carts, cart_members, schedules, logs, …)
- **frontend/**
  - [app-shell.md](4-capabilities/frontend/app-shell.md) — SPA shell, theme, i18n, pages
  - [auth-manager.md](4-capabilities/frontend/auth-manager.md) — the token manager (single-flight refresh)
  - [plugin-discovery.md](4-capabilities/frontend/plugin-discovery.md) — generated registry + dynamic routing

### Cross-cutting sections

- **[api/](api/)** — HTTP API
  - [README.md](api/README.md) — conventions and Swagger
  - [endpoints.md](api/endpoints.md) — the implemented endpoints
- **[infrastructure/](infrastructure/)** — pipeline, environment and operations
  - [build-system.md](infrastructure/build-system.md) — monorepo layout and the two-image build
  - [ci.md](infrastructure/ci.md) — CI, dev images, publish on tag, versioning
  - [deployment.md](infrastructure/deployment.md) — pull-based deploy and the deploy kit
  - [dev-container.md](infrastructure/dev-container.md) — zero-install development environment
  - [configuration.md](infrastructure/configuration.md) — how the system is configured (bootstrap + DB-first)
  - [backup-and-restore.md](infrastructure/backup-and-restore.md) — backing up and restoring data
- **[developer-rules/](developer-rules/README.md)** — code and quality rules
  - [backend/rules.md](developer-rules/backend/rules.md), [frontend/rules.md](developer-rules/frontend/rules.md), [infrastructure/rules.md](developer-rules/infrastructure/rules.md), [plugins/rules.md](developer-rules/plugins/rules.md), [documentation/rules.md](developer-rules/documentation/rules.md)
- **[plugin-development/](plugin-development/manifest-reference.md)** — building plugins
  - [manifest-reference.md](plugin-development/manifest-reference.md) — the `manifest.json` contract
- **[implemented-plugins/](implemented-plugins/README.md)** — the real plugins of this install
  - **dragon-store/** — the first scraper: [overview.md](implemented-plugins/dragon-store/overview.md), [features.md](implemented-plugins/dragon-store/features.md), [capabilities.md](implemented-plugins/dragon-store/capabilities.md)
- **[env-variables.md](env-variables.md)** — every `WEA_`-prefixed environment variable
- **[updates/](updates/README.md)** — plain-language, per-phase "what can it do now" recaps: [phase-00](updates/phase-00.md), [phase-01](updates/phase-01.md), [phase-02](updates/phase-02.md), [phase-03](updates/phase-03.md), [phase-04](updates/phase-04.md), [phase-05](updates/phase-05.md), [phase-06](updates/phase-06.md)
- **[future-improvements/](future-improvements/README.md)** — forward-looking **ideas to revisit after 1.0** (ideas, not todos; not tied to any phase)

### Spec-ahead (not yet implemented)

The parts of the product not yet built live, in Italian, under [`../docs-ita/`](../docs-ita/README.md):
the full [development-flow](../docs-ita/development-flow/README.md) roadmap, the
[notification-architecture](../docs-ita/2-architecture/notification-architecture.md), and the
alert/summary/notifier slices across every layer. They migrate here as each phase lands.
