# Price history (recording)

> **Layer 3 — User feature** · Audience: architects, developers.
>
> English translation of the Italian reference [`docs-ita/3-features/user/price-history.md`](../../../docs-ita/3-features/user/price-history.md), limited to what is implemented (DOC-12). Phase 3 ships the **append-only recording** of price and availability changes — the data on which everything later is built; phase 8 adds the user-facing **charts** (product and cart views, Week/Month/All, cart projection), documented below. The derived indicators (all-time low, statistics, value judgement) are a separate feature, [price-analytics](../../../docs-ita/3-features/user/price-analytics.md) (later phase). Capability: [price-history](../../4-capabilities/core/price-history.md).

## Purpose

To capture, over time, the evolution of prices and availability, so a future view can judge whether today's offer is a real low. The recording is the foundation; the charts that read it come later.

## Recording principle (simplified by design)

The history records an entry **only when something changes**: the price **or** the availability. No periodic snapshots. Each entry carries the current price, the list price, the discount and the availability state: a single append-only table covers both the price line and the periods of unavailability, with no extra infrastructure.

## Requirements

- **HIST-R1** — The entry is written by the **core** on a change of price **or** availability; never by the scraper directly. It is the Catalog Update Service that, comparing the incoming scrape against the last known state, appends a row when either has moved.
- **HIST-R5** — A product's history has **no automatic retention**: the value of the history grows over time and is the very reason the system exists. It is removed only together with its product (catalog cleanup) — that cascade cleanup arrives with the catalog mutation actions in a later phase.

## Reading the series (design note)

The entries are **change points**: a consumer joins them as a step line (the price stays constant between two changes). An interval with no entry does not mean "missing data": it means "nothing changed". This is what makes the recording cheap and the long-range view meaningful — the property the charts render.

## Charts (phase 8)

Two views, **one** chart component (only the data source differs), reached from a **Price history**
page and, in context, from the Product Picker (a per-row chart icon) and a cart's page (a *view
chart* action). Deep-linked via `?product=` / `?cart=`.

- **HIST-R2** — The product chart shows the **discounted price** line; where the product was
  unavailable the line shows an **explicit gap** (no interpolation), derived from the recorded
  availability.
- **HIST-R3** — Time selectors: **Week** (7 days), **Month** (30 days), **All**.
- **HIST-R4** — The cart chart projects the cart's **current composition** onto the history: the
  sum of the current members' discounted prices, each excluded during its unavailable intervals.
  *Declared simplification*: the past composition (who was in the cart when) is not reconstructed.
- **HIST-R6** — Reached from the Product Picker (row → product chart), a cart's page (action →
  cart chart) and the Price history page.

The series are served ready to plot by the backend ([price-history capability](../../4-capabilities/core/price-history.md), [endpoints](../../api/endpoints.md#price-history--price-history)); the chart renders steps and gaps and animates range changes smoothly.
