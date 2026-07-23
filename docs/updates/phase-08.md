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

_Nothing merged yet — entries land here as each MVP ships._

<!--
As MVPs land, document them here in the same user-facing voice as the earlier phases, e.g.:

### 1) Product history series (step line + availability gaps)
### 2) Cart history series (stepped sum of the current composition)
### 3) The chart component (ranges, tooltip, light/dark)
### 4) The Price-history page + entry points from the Picker and the cart card

_Under the hood:_ …
-->

## Good to know

- **Gaps are explicit, not interpolated.** Where a product was unavailable the line breaks — the
  chart never draws a price through an out-of-stock stretch.
- **No new data is collected.** The series come from the `price_history` written on every scrape
  since phase 3; this phase only reads and draws it. Price history is never pruned.

## Useful Commands

```bash
docker compose -f compose-dev.yml up -d --build         # db + web + worker + pgweb + mailpit
```
