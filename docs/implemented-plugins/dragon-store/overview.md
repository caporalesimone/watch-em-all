# Dragon Store — Overview

> **Implemented plugin — Dragon Store (scraper)** · Audience: developer.
>
> English translation of the Italian reference [`docs-ita/implemented-plugins/dragon-store/overview.md`](../../../docs-ita/implemented-plugins/dragon-store/overview.md), limited to what is implemented (DOC-12). It introduces the system's first scraper and what it monitors today: a single product page on `dragonstore.it`.

## What it does

Monitors prices and availability of products on `dragonstore.it` (board games, trading cards and the like). It is a concrete implementation of the [Scraper Plugin](../../3-features/plugins/scraper-plugin.md): all the site knowledge — accepted inputs, category navigation, pagination, special product states, discount rules — lives inside the plugin; the core only ever receives `Product`.

In phase 3 the implemented surface is the **single product page** (`kind=product`): real scraping of one `.gp` product page via `context.http`. Category/listing inputs, pagination and the "dented" filter described below are forward-looking and arrive in a later phase (phase 9).

## Audience

The typical user is the collector from use case [UC-1](../../../docs-ita/1-business/use-cases.md): they keep an eye on a wishlist on the store and buy in bulk when the overall saving (threshold discounts included) satisfies them.

## At a glance

| Aspect | Choice |
|---|---|
| User input | URL of a **single product** (implemented in phase 3) and URL of a **category** (enumerated with pagination — arrives in phase 9) |
| Site exclusions | **"dented"** (damaged) products: excluded **by default**, includable with a **per-category** toggle; a dented item added as a single product is always included (explicit choice, flagged in red in the UI) — arrives in phase 9 |
| Out-of-stock | included with `is_available=false` (contract) |
| Adjustments | **threshold discounts** on the cart total (store rules), configurable by the admin — arrives in a later phase |
| Product identity | the site's **native numeric ID** (present in the `.gp.<id>.uw` URLs and in the cards) — verified in pre-analysis, see [capabilities](capabilities.md) |
| Technical strategy | **server-rendered** pages (classic ASP): HTTP + HTML parsing, no headless browser |

## Known site characteristics

- Listing pages are **server-rendered** with prices and availability already in the HTML; AJAX only for sorting and view changes (pre-analysis: see [capabilities](capabilities.md)).
- Products in special states ("dented") are published as **separate listings** with a title prefix and reduced price: excluded by default from monitoring, includable at the user's choice (per category, or by adding them explicitly as a single product) — this filtering arrives in phase 9.
- Threshold discount rules on the cart total (e.g. −10% above 50 €, −15% above 100 €) — arrives in a later phase.

## Documents

| Document | Content |
|---|---|
| [features.md](features.md) | Detailed behaviour: inputs, user/admin UI, dedup, filters |
| [capabilities.md](capabilities.md) | Tables, run flow, scraping strategy, open points |
