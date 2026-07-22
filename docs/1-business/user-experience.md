# The user's experience

> **Layer 1 — Business / UX** · Audience: everyone · Descriptive text only.
>
> English mirror of the Italian reference [`docs-ita/1-business/user-experience.md`](../../docs-ita/1-business/user-experience.md), limited to what is implemented (DOC-12). It tells the realized journey: first login, telling the system what to watch, and building carts. The parts that depend on not-yet-built capabilities — receiving notifications, the price-history/statistics pages, catalog cleanup, and data export — stay in the Italian document. The functional details are in the [Layer 3 — user features](../3-features/user/).

## First login

The user receives their credentials (username and temporary password) from the administrator. At first login the system forces a password change. (The interface is in English: language selection is provided for by the design but not offered in the first version.) The interface is a modern web application, with a dark theme by default (switchable to light from the Profile) and a side navigation bar always present: **Dashboard**, **Product Picker** (Catalog), **Carts**, **Profile** and — at the bottom, in a group of its own — the list of supported sites (the scrapers).

The Dashboard is the landing page: it welcomes the user by name. *(Its cart-status summary arrives together with the alerting phases.)*

## Telling the system what to watch

The user opens a scraper's page from the group at the bottom of the side bar. Here each site has its own interface, designed for that site: typically the user can preview the products (a "dry run" that saves nothing) and then select what to monitor — individual products, whole categories, or whatever the site allows. From then on, at every scheduled execution, the scraper extracts the chosen products and deposits them into the user's **personal catalog**. When the catalog is empty a per-scraper **"Scrape now"** on the scraper's page populates it right away, without waiting for the next scheduled run.

## Building the carts

With the catalog populated, the user creates carts from the Carts page: they give a name and choose the mode — **tied to a single site** (with totals computed the way that site would compute them: threshold discounts, shipping) or **cross-store** (products from different sites, even the same product repeated once per site). The mode is immutable once set.

Then they open the **Product Picker**: a table of their catalog, sortable and filterable, where every row shows photo, title, prices, discount and — always — **the provenance icon of the source site**. They select the rows and add them to the chosen cart; the target cart's membership rules apply on the server (own catalog only, no delisted products, a single currency, and — for a single-site cart — only that scraper's products).

On the cart the user finally sets the **threshold** ("tell me below €300", or entered as a % that mirrors the € value on screen). The cart then shows its computed state: full and discounted totals, the shop's adjustments (single-site carts), the final estimate, and whether the threshold has been reached. Clicking a cart opens its **detail page** — the full product table with preview images, per-row provenance and per-row removal.
