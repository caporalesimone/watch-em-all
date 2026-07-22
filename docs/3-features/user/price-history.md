# Price history (recording)

> **Layer 3 — User feature** · Audience: architects, developers.
>
> English translation of the Italian reference [`docs-ita/3-features/user/price-history.md`](../../../docs-ita/3-features/user/price-history.md), limited to what is implemented (DOC-12). Phase 3 ships the **append-only recording** of price and availability changes — the data on which everything later is built. The user-facing **charts** (product and cart views, time selectors, cart projection) arrive in phase 8 and are documented only in the Italian reference. The derived indicators (all-time low, statistics, value judgement) are a separate feature, [price-analytics](../../../docs-ita/3-features/user/price-analytics.md) (later phase). Capability: [catalog-update-service](../../4-capabilities/core/catalog-update-service.md).

## Purpose

To capture, over time, the evolution of prices and availability, so a future view can judge whether today's offer is a real low. The recording is the foundation; the charts that read it come later.

## Recording principle (simplified by design)

The history records an entry **only when something changes**: the price **or** the availability. No periodic snapshots. Each entry carries the current price, the list price, the discount and the availability state: a single append-only table covers both the price line and the periods of unavailability, with no extra infrastructure.

## Requirements

- **HIST-R1** — The entry is written by the **core** on a change of price **or** availability; never by the scraper directly. It is the Catalog Update Service that, comparing the incoming scrape against the last known state, appends a row when either has moved.
- **HIST-R5** — A product's history has **no automatic retention**: the value of the history grows over time and is the very reason the system exists. It is removed only together with its product (catalog cleanup) — that cascade cleanup arrives with the catalog mutation actions in a later phase.

## Reading the series (design note)

The entries are **change points**: a consumer joins them as a step line (the price stays constant between two changes). An interval with no entry does not mean "missing data": it means "nothing changed". This is what makes the recording cheap and the long-range view meaningful — the property the phase-8 charts will render.
