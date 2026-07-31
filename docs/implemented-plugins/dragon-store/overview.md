# Dragon Store — Overview

> **Implemented plugin — Dragon Store (scraper)** · Audience: developer.
>
> Limited to what is implemented (DOC-12). It introduces the system's first scraper and what it monitors today on `dragonstore.it`: a single product page, or a whole category.

## What it does

Monitors prices and availability of products on `dragonstore.it` (board games, trading cards and the like). It is a concrete implementation of the [Scraper Plugin](../../3-features/plugins/scraper-plugin.md): all the site knowledge — accepted inputs, category navigation, pagination, special product states, discount rules — lives inside the plugin; the core only ever receives `Product`.

Both inputs are implemented: a **single product page** (`kind=product`, one `.gp` page) and a **category** (`kind=category`, a `.sp` listing walked page by page through the site's own `&pg=N`). A category is one input that yields dozens of products per run, which is what the scraper exists for; the "dented" filter below decides which of them are wanted.

## Audience

The typical user is the collector from use case [UC-1](../../../docs-ita/1-business/use-cases.md): they keep an eye on a wishlist on the store and buy in bulk when the overall saving (threshold discounts included) satisfies them.

## At a glance

| Aspect | Choice |
|---|---|
| User input | URL of a **single product**, or URL of a **category**, enumerated in full with pagination on every run |
| Site exclusions | **"dented"** (damaged) products: excluded **by default**, includable with a **per-category** toggle (at add time or later, effective from the next scan); a dented item added as a single product is always included — an explicit choice, and its row says so, because the title arrives with the label stripped |
| Out-of-stock | included with `is_available=false` (contract) |
| Adjustments | **implemented (phase 5)**: a non-cumulative **threshold discount** + **shipping** (free above a threshold) on the cart total (store rules); the phase-5 values live in `adjustments.py`, becoming admin-editable later |
| Product identity | the site's **native numeric ID** (present in the `.gp.<id>.uw` URLs and in the cards) — verified in pre-analysis, see [capabilities](capabilities.md) |
| Technical strategy | **server-rendered** pages (classic ASP): HTTP + HTML parsing, no headless browser |

## Known site characteristics

- Listing pages are **server-rendered** with prices and availability already in the HTML; AJAX only for sorting and view changes (pre-analysis: see [capabilities](capabilities.md)).
- Products in special states ("dented") are published as **separate listings** with a title prefix and reduced price: excluded by default from monitoring, includable at the user's choice (per category, or by adding them explicitly as a single product).
- Since **25 July 2026** the site gates the first request of every session behind an anti-bot interstitial served as **HTTP 200**, so the status code is no evidence and the body has to be classified. `robots.txt` publishes no `Disallow` and asks `Crawl-delay: 10`, which the core client enforces — that delay is why a large category takes minutes and why the manual scrape is a privilege (see [capabilities](capabilities.md)).
- Threshold discount rules on the cart total, applied as cart **adjustments** (implemented in phase 5): a single, non-cumulative band (the highest reached — `≥100 €→5%`, `≥200 €→10%`, `≥300 €→15%`) plus shipping (`+5.00 €`, free above `100 €`).

## Documents

| Document | Content |
|---|---|
| [features.md](features.md) | Detailed behaviour: inputs, user/admin UI, dedup, filters |
| [capabilities.md](capabilities.md) | Tables, run flow, scraping strategy, open points |
