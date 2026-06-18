# Plugin Context

> **Layer 4 — Capability** · Audience: developer.
>
> English translation of the Italian reference [`docs-ita/4-capabilities/core/plugin-context.md`](../../../docs-ita/4-capabilities/core/plugin-context.md), limited to what is implemented (DOC-12). Phase 2 ships the **minimal** context (DB, logger, config). The HTTP client (politeness, cache), `update_catalog` and the Markdown helper arrive with the scraper/notifier runtime in later phases.

## Purpose

The object handed to every plugin in `initialize()`: what the plugin may use and, by convention, nothing else. It is an architectural discipline (clear boundaries, testability), not a security boundary — plugins are trusted first-party code.

## Contract (phase 2)

```python
@dataclass
class PluginContext:
    engine: Engine             # to create the plugin's OWN tables (own MetaData)
    db: Session                # a session scoped to the plugin's own tables (plugin_<name>_*)
    logger: Logger             # namespaced per plugin
    config: Mapping[str, Any]  # the plugin's admin-config section
```

The default factory wires the core engine, a fresh session, a per-plugin namespaced logger (`wea.plugin.<name>`), and an empty config. The registry injects it; tests can inject their own.

## The DB session and engine

- The plugin manages **only** its own tables (`plugin_<name>_*`), which it creates idempotently in `initialize()` — typically with its **own** SQLAlchemy `MetaData` and `metadata.create_all(context.engine)`, fully separate from the core schema.
- It never writes core tables; by convention it does not read tables that are not its own.

## Declared phase-2 simplifications (flow rule #7)

- **`logger`** writes to **stdout** for now. The `system_log` table (where plugin `warning`/`error` messages will land, visible in the admin page) arrives around phase 10; only the sink changes then — the `ctx.logger` contract is already stable.
- **`config`** is **empty** for now. The two-level configuration (admin/user `ConfigField` schemas, the `scraper_admin_config` / `notifier_admin_config` tables) arrives in phases 7/9/10.

These are explicit, contract-stable stubs: plugin code calls `ctx.logger`/`ctx.config` exactly as it will later.
