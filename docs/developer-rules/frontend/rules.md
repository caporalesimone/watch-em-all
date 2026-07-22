# Developer Rules — Frontend (Svelte/TypeScript)

> Binding for the SPA and for the plugin frontends. Capability: [app-shell](../../4-capabilities/frontend/app-shell.md).

## Style and types

- **FE-1** — TypeScript **strict**; `eslint`, `prettier` and `svelte-check` clean in CI. No `any` in shared modules. Fixed baseline: **SvelteKit 2 (Svelte 5, runes)**, **Tailwind CSS 4**, **Node 22 LTS** ([build-system](../../infrastructure/build-system.md)).
- **FE-2** — Small, single-responsibility components; non-trivial logic lives in testable TS modules, not in the component scripts.
- **FE-3** — Naming: `PascalCase.svelte` for components, `camelCase` for functions/stores, kebab-case for routes.

## SPA architecture

- **FE-4** — **Never a direct `fetch`**: every call goes through the `lib/api/` client (typed per endpoint), which uses the [Auth Manager](../../4-capabilities/frontend/auth-manager.md). No component knows about the tokens.
- **FE-5** — Shared state only in the `lib/stores/` stores; stores do no I/O by themselves (the actions that populate them do).
- **FE-6** — API response types aligned with the Pydantic contracts (Decimal = string!), validated with Zod at the boundary when the data drives critical logic (prices, thresholds).
- **FE-7** — Potentially long lists (catalog, histories, runs): **always** server-side pagination; never load "everything" and filter on the client.

## Design system and UX

- **FE-8** — Reusable components in `$lib/components`; a pattern used twice is extracted. Plugins **must** use the design system (no parallel styles).
- **FE-9** — Tailwind with class-based dark mode; every component is tested in both themes; dark default, theme applied before the first render (no flash).
- **FE-10** — **Provenance** (the scraper icon) is shown everywhere a product appears: Product Picker, carts, notifications, previews. Not optional (UC-2).
- **FE-11** — Destructive actions (clear catalog, delete cart/account): confirmation with **explicit consequences** in the text.
- **FE-12** — Curated empty states: empty catalog (with scrape-now), no carts, no notifications — never a blank table without guidance.

## i18n and formats

- **FE-13** — No hard-coded strings in components: everything from translation keys in the **`i18n/`** folders (core or plugin namespace), via **svelte-i18n** (dictionaries registered at runtime, per-plugin namespaces loaded lazily). **V1 ships only `en`** (English-first): every new string is born in `en.json`, which must always exist and be complete (it is the **fallback** when a language is missing); the other languages are a future fill-in of the files, never a refactor. Never build sentences by concatenating keys (word order changes between languages): always whole templates with placeholders.
- **FE-14** — Dates with Day.js; prices formatted by a single utility (currency symbol, 2 decimals); mind the weekday convention (0=Monday from the backend ↔ JS `getDay()` starts from Sunday: mapped in a single place).

## Plugin frontend

- **FE-15** — Entry contract: `export default { component }`. The route comes from the manifest, never declared in the code.
- **FE-16** — Imports from the core only via `$lib` (design system, stores, api client); never relative paths towards the app.
- **FE-17** — A plugin's translations live in its own namespace; never touch the core's language files.
- **FE-18** — Widgets **candidate for sharing** between plugins (e.g. **Scrape-now**, the **dry-run** table [SCR-R12](../../3-features/plugins/scraper-plugin.md), the **dynamic config form** 7.F1, Test/Send buttons, popups/overlays, status chips) are written **self-contained and props-driven**, with no coupling to the single plugin, so that extracting into `$lib/components` at the **second use** (FE-8) is a simple move and not a refactor. Their i18n strings, once extracted into the core, live in a **shared core namespace** (e.g. `ui.*`), not duplicated per-plugin (FE-13/FE-17). As long as there is **one** consumer the abstraction stays premature: the component is kept local but already decoupled, ready to lift.
