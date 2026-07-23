# Phase 8 — Price-history charts 📈

> Feature-level recap. Phase 8 surfaces the treasure the system has been quietly accumulating
> since phase 3: the **price and availability history**. From the Product Picker you'll open a
> product's chart — a step line of its price with the gaps where it was out of stock, and
> Week / Month / All range selectors; from a cart card, the trend of its total. One chart
> component, two data sources (product and cart).
>
> 🚧 **In progress (0.8.x).** This page fills in as the phase's MVPs ship; the list below tracks
> what has actually landed.

## What's implemented (0.8.0)

### 1) Product history series (step line + availability gaps)

`GET /api/products/{id}/history?range=week|month|all` serves a product's price as a **step
series** — the price holds flat between changes — with an **explicit gap** over every stretch the
product was out of stock (the line breaks; it is never drawn through unavailability). For the
Week/Month windows the value in effect at the window start is carried in (clamped to the edge) so
the line starts at the right price, not at zero. It's your own catalog only — someone else's
product id is a 404.

### 2) Cart history series (stepped sum of the current composition)

`GET /api/carts/{id}/history?range=…` serves the cart's **total over time**: the sum of its
current members, each counted only while it was available (out-of-stock members drop out of the
total for those stretches). The cart's *current* composition is projected onto the past — we don't
reconstruct who was in the cart on a past date (a declared simplification).

### 3) The chart component (ranges, tooltip, light/dark)

One chart component drives both views (built on Chart.js). Week / Month / All selectors, a hover
tooltip (date + price, and “out of stock” on a gap), and it reads cleanly in both themes. Range
and data changes **animate smoothly** rather than snapping.

### 4) The Price-history page + entry points

A new **Price history** page (sidebar) with a Product | Cart toggle and a picker. You also reach it
in context: a **chart icon** on each Product Picker row opens that product's chart, and a **View
price chart** action on a cart's page opens the cart's total. Both deep-link (`?product=` /
`?cart=`), so the page opens on the right series.

_Under the hood:_ the series come from a small read-side helper over the append-only
`price_history`; the SPA never aggregates. No new data is collected — this phase only reads and
draws what has been recorded since phase 3.

## Good to know

- **Gaps are explicit, not interpolated.** Where a product was unavailable the line breaks — the
  chart never draws a price through an out-of-stock stretch.
- **No new data is collected.** The series come from the `price_history` written on every scrape
  since phase 3; this phase only reads and draws it. Price history is never pruned.

## Useful Commands

```bash
docker compose -f compose-dev.yml up -d --build         # db + web + worker + pgweb + mailpit
```
