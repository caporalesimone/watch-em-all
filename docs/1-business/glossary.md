# Glossary

> **Layer 1 — Business** · Audience: everyone.
>
> English mirror of the Italian reference [`docs-ita/1-business/glossary.md`](../../docs-ita/1-business/glossary.md), limited to what is implemented (DOC-12). It defines the terms already in use in the realized product (phases 0–5). The terms that name not-yet-built capabilities — alert digest, summary, cadence, baseline, alert history, price history, all-time low, value indicator, deferred deletion, data export — stay in the Italian document.

| Term | Definition |
|---|---|
| **Scraper** | Plugin that observes a single e-commerce site and extracts products (prices, availability). Internally it works **sequentially** (a single workflow per scraper); the system also runs scrapers **one at a time**, each at its own scheduled time. |
| **Notifier** | Plugin family that delivers notifications over a channel (email, Discord, …). The plugin type is part of the architecture today (listed in the admin's informational Notifiers menu); actual delivery arrives in a later phase. |
| **Plugin** | Self-contained full-stack unit (backend + interface) that extends the system. Two families: scraper and notifier. Every plugin is configurable at **admin** level (system parameters) and at **user** level (personal parameters). |
| **Catalog** | The set of products extracted for a user. Personal and isolated per user. |
| **Product Picker** | The catalog table from which the user selects the products to put into carts. Distinct from the individual scraper pages (where the user chooses *what to observe on the site*). |
| **Cart** | Group of catalog products with a savings threshold. The minimal unit of monitoring. |
| **Cart mode** | `scraper_specific`: products from a single site, totals computed with that site's rules (adjustments). `cross`: products from different sites, even the same product repeated once per site; no adjustments; **provenance always shown** per row. Immutable after creation. |
| **Adjustment** | Corrective line on a scraper-specific cart's total, computed by the plugin: a threshold discount (positive) or an added cost such as shipping (negative). |
| **Threshold** | An absolute **€ value** (`threshold_amount`) below which the cart is considered "on sale"; `null` = no threshold. The **percentage** is only a UI input aid that mirrors the € value on screen — only the € value is sent to the backend. |
| **Provenance** | The site/scraper a product comes from. Always shown (icon + name) in the Product Picker, in the cart cards and in the cart detail — indispensable in cross carts. |
| **Product identity** | How the system recognizes "the same product" from one observation to the next: a stable identifier provided by the scraper (`external_id`), together with the plugin and the user. |
| **Unavailable (`is_available = false`)** | Product temporarily out of stock on the site. It stays in the catalog and in the carts, excluded from the totals until it returns. Decided by the **scraper**. |
| **Delisted (`removed`)** | Product that has disappeared from the site (no longer found by the scraper). It stays in the catalog, greyed out and ignored, until the user cleans it up manually. Decided by the **core**. |
| **Run (of a scrape)** | A single execution of a scraper, which processes all the users who have configured it. Scheduled by the admin, from 1 to N times a day. |
| **Slot** | One of a run's scheduled times. If the system was down, it recovers the most recent missed slot (only one). |
| **Scrape cache** | The reuse of the results of a recent search: the same query, across different users or close-together runs, does not go back to the site until the **half-life** (validity duration, configured by the admin per plugin) expires. |
| **Core** | The heart of the system: it orchestrates the plugins, owns the data, computes carts. It does not know the plugins' internal logic (nor, for example, the notion of "category", which is internal to the scrapers). |
| **Worker** | The process that runs things at the right moment: scraper executions (and, later, notifications and reports). |
