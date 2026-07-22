# Plugin architecture and dynamic integration

> **Layer 2 — Architecture** · Audience: SW architects, system engineers.
>
> English translation of the Italian reference [`docs-ita/2-architecture/plugin-architecture.md`](../../docs-ita/2-architecture/plugin-architecture.md), limited to what is implemented (phases 0–5, DOC-12). The dynamic **backbone** (discovery, validation, isolated loading, dynamic frontend mounting), the scraper runtime (identity, `run_for_user`/`run_test`, `get_adjustments`), the `update_catalog` write path and the polite HTTP client all ship. The remaining contracts — the **two-level user configuration** (declarative `ConfigField` schemas) and the **notifier** `send`/config contracts — arrive in later phases and are described in the Italian reference.

## The principle: plugin-first, full-stack

A plugin is an **indivisible full-stack unit**: Python backend and Svelte frontend co-located in one folder, described by a declarative **manifest** that is the plugin's single source of truth (identity, type, activation, entry points, icon, translations, contract version).

Two families derive from a common base:

```mermaid
classDiagram
    class BasePlugin {
        <<abstract>>
        plugin_id
        initialize(context)
        router()
        delete_user_data(context, user)
    }
    class ScraperPlugin {
        identity_seed(raw)
        run_for_user(context, user)
        run_test(context, params)
        configured_users(context)
        get_adjustments(products, cart_total)
    }
    class NotifierPlugin
    BasePlugin <|-- ScraperPlugin
    BasePlugin <|-- NotifierPlugin
```

The base contract is minimal — `initialize`, `router`, `delete_user_data` (all with safe defaults). The **scraper** family adds the shipped runtime: the abstract `identity_seed` (the only site-specific point of the product identity; a scraper that omits it does not load), the `run_for_user`/`run_test` entry points, `configured_users` (whom a scheduled run iterates), and `get_adjustments` (site-specific cart rules). The **notifier** family is still a marker: its `send` and config-schema contracts land in later phases.

## Dynamic integration — backend

At startup every container that loads plugins (`web` and `worker`) runs the same deterministic sequence. **No runtime plugin switching**: activation is static via the manifest, and a change needs a rebuild + restart.

```mermaid
flowchart TD
    A[Scan scrapers/ and notifiers/] --> B[Read + validate manifest<br/>type vs folder, api_version, name]
    B --> C{enabled?}
    C -- no --> X[Ignored]
    C -- yes --> D[Dynamic import of the backend entry]
    D --> E[initialize with a dedicated Plugin Context<br/>the plugin creates its own tables]
    E --> F[Register the plugin router<br/>under /api + route_base]
    F --> G[Active]
    D -- error --> Y[Rejected, logged error<br/>core and other plugins unaffected]
```

Registry guarantees: manifest validation (type matches the folder, `api_version` compatible with the core, unique `name` equal to the class's `plugin_id`), and **failure isolation** — a broken plugin does not load, the rest does. See [plugin-registry](../4-capabilities/core/plugin-registry.md).

## Dynamic integration — frontend

The plugin frontends are part of the **same build** (one Vite process): a build step reads the manifests, filters the enabled plugins, and generates the component registry; at runtime the SPA asks the backend for the active plugins and mounts their routes dynamically.

```mermaid
flowchart LR
    subgraph "Build time"
        M[manifest.json] --> GEN[Generate the frontend registry]
        GEN --> V[Unified Vite build<br/>app + plugin components]
    end
    subgraph "Runtime"
        SPA[SPA] -->|GET /api/plugins| API[Enabled plugins<br/>name, type, route_base, icon]
        API --> RT[Dynamic routes<br/>route_base → lazy component]
    end
    V -.bundle.-> SPA
```

Key properties:

- **Adding a plugin does not touch build or routing code**: a folder with a valid manifest and a conforming frontend entry is enough.
- Plugins import the core design system and shared helpers **via `$lib`** (single build, no cross-bundle issue) — never a bare dependency, which would not resolve from outside the SvelteKit root.
- Each plugin brings its own **translations** (a dedicated namespace) and an **icon**.
- Build and runtime stay coherent by construction (the same manifests feed both); this is why activation needs a rebuild (see [build system](../infrastructure/build-system.md)) and why a bundle/runtime skew is surfaced rather than crashing (see [plugin-discovery](../4-capabilities/frontend/plugin-discovery.md)).

## Isolation: the "soft sandbox"

Each plugin receives a **Plugin Context** with what it needs and, by convention, nothing else: a DB session/engine for its **own** tables, a namespaced logger, the `update_catalog` callback (a scraper's only write path to the catalog), and a polite, counted, retrying HTTP client backed by the per-plugin scrape cache. The plugin's own declared config stays empty until the `ConfigField` infrastructure lands (later phase). See [plugin-context](../4-capabilities/core/plugin-context.md).

**Declared trust model**: plugins run in-process and are **trusted first-party code**. The context is an architectural discipline (maintainability, clear boundaries), **not** a security boundary — Python cannot stop a malicious plugin from reaching whatever it wants. The real protections against *faulty* (not malicious) plugins are error isolation at load, namespaced tables, the per-scraper run timeout and the anti-overlap DB lock. Consistent with the project's security posture.

## Plugin data rules

- Every plugin owns **one or more dedicated tables** (namespaced `plugin_<name>_*`) that it creates itself, idempotently, at initialization. No shared generic tables.
- The core never reads a plugin's tables; when it needs something it **asks the plugin** through a contract.
