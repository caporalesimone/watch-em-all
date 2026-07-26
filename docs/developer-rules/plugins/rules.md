# Developer Rules — Plugins

> **Additional** rules (on top of the backend and frontend rules) for plugin code. Guide: [plugin-development/](../../../docs-ita/plugin-development/README.md).

## Boundaries

- **PLG-1** — All network I/O goes through `context.http`: never a private HTTP library, never parallel sessions. Politeness and request counting belong to the core, non-negotiable.
- **PLG-2** — DB: only the plugin's own `plugin_<name>_*` tables, created idempotently in `initialize()`. Never read or write the core's tables or another plugin's; the catalog is fed **only** via `update_catalog`.
- **PLG-3** — No filesystem access outside the plugin's own folder, no environment variables, no process-global state. Everything needed arrives from the `PluginContext`.
- **PLG-4** — Logs only via `context.logger`; never users' operational content in the messages.

## Behaviour

- **PLG-5** — Single-thread by contract: no internal threading/asyncio towards the site. Long work must be interruptible (the runner's run timeout must be able to stop you — and with serial execution a hung job also holds up the queue).
- **PLG-6** — *withdrawn in 0.9.0.* It required `run_test`/dry-run to write nothing; both the method and the concept are gone (see [scraper-plugin](../../3-features/plugins/scraper-plugin.md), SCR-R11/R12 withdrawn). The number is retired, not reused.
- **PLG-7** — `external_id`: the plugin implements **only** the abstract seed `identity_seed` (SCR-R10); hashing/normalization is imposed by the base (`final`) and **never reimplemented**. The choice of seed is documented in the plugin's doc under `implemented-plugins/`; changing it is a breaking change for users' data and is done only with a migration note. Never fill `external_id` by hand or hash with the built-in `hash()`.
- **PLG-8** — Per-run idempotency: two consecutive runs with no changes on the site produce **zero** delta (it is the checklist's check and symptom #1 of an unstable `external_id`).

## Quality

- **PLG-9** — The core's contract suite ([checklist-and-testing](../../../docs-ita/plugin-development/checklist-and-testing.md)) is mandatory and passes in CI; parsing tests use saved fixtures, never the real site.
- **PLG-10** — Complete manifest (incl. the current `api_version` and the icon) and routes documented in the Swagger with the tag `Plugin: <name>`.
- **PLG-11** — Documentation in `implemented-plugins/` before release: overview + specific details + open points. An undocumented plugin is not enabled.
- **PLG-12** — Respect for the observed site: no bypassing of explicit protections (captcha, blocks), honest identification in the default user-agent, minimal necessary request volumes. When in doubt about the lawfulness of observing a site, the doubt wins.
