# Phase 5 — Carts (the functional heart)

> Feature-level recap. Phase 5 delivers **carts** — the reason the catalog exists: group
> products, see what they'd really cost, and set a savings target. It ships the **two cart
> modes** (cross-store and single-store), the **membership rules**, a read-only **Cart
> Engine** (computed totals, the shop's adjustments, a final estimate and a health flag),
> the **€ savings threshold** with the € ↔ % mirror, the **Dragon Store** discount/shipping
> adjustments, and the **cart detail page** built on a small set of shared presentation
> widgets. A throwaway **TP Scraper** data generator gives a second product source for
> testing cross carts by hand. Opened with some catalog polish; closed with two fixes.

## What's implemented (0.5.0)

### 1) Carts — two modes

- A cart groups catalog products and shows what they'd really cost. There are two kinds,
  chosen at creation and **immutable** afterwards (CART-R2 — changing the mode would
  invalidate its adjustments, so you recreate it instead):
  - **Cross-store** (`cross`): products from **any** shop. The *same* product can appear
    **once per shop** — the intended way to watch one item across sites (UC-2). Every row
    shows its store (CART-R6).
  - **Single-store** (`scraper_specific`): products from **one** shop, with **that shop's
    adjustments** applied — the total is "what you'd really pay there" (UC-1).
- Deleting a cart deletes only the cart (never the catalog products), with confirmation
  (CART-R3).

### 2) Membership rules

- You fill a cart from the **Catalog** (Product Picker): select rows, pick a target cart,
  add. The add is validated as a batch — the whole request succeeds or is rejected:
  - your **own catalog** only (`422 product_not_found`);
  - **delisted** products can't be added (`422 product_delisted`); **out-of-stock** ones
    can (they just don't count toward the totals);
  - a **single-store** cart accepts only **that scraper's** products
    (`422 product_scraper_mismatch`);
  - a cart holds a **single currency** (`422 currency_mismatch`) — V1 neither converts nor
    aggregates currencies;
  - adds are **idempotent** (a product already in the cart is not duplicated), removing a
    non-member is a no-op.

### 3) The Cart Engine — computed state

- A **read-only** engine computes each cart's economic state on demand (it persists
  nothing): the **full total** (Σ list prices) and **discounted total** (Σ current prices)
  over the **active** members, the shop's **adjustments** (single-store only), the **final
  estimate** (= discounted − Σ adjustments), and a set of flags for the card — `has_delisted`
  ("unhealthy" cart), `any_on_sale` / `all_on_sale`, and the cart's single `currency`.
- **Active** = available **and** not delisted; unavailable/delisted members stay in the
  cart but are **excluded from every total** until they come back (CART-R8).

### 4) The € savings threshold (with the € ↔ % mirror)

- Each cart can carry a **savings threshold**, stored as an **absolute € value**
  (`threshold_amount > 0`, or none). In the UI you can enter it **in € or as a %**, and the
  two fields **mirror each other** on the current full total (`threshold = full · (1 −
  pct/100)`) — but **only the € value is sent** to the backend. The percentage is purely an
  input aid; the backend never sees it (CART-R9/R10).
- The engine marks the threshold **reached** when the **final estimate** drops to it
  (CART-R11), and **partial** when it's reached while some members are excluded. No threshold
  event fires when the cart has **no active product** (CART-R12).

### 5) Dragon Store adjustments

- For a **Dragon Store** single-store cart the engine applies the shop's real cart rules
  (DRG-R5), each shown as its own signed line in the cart:
  - a **non-cumulative threshold discount** — 5% over €100, 10% over €200, 15% over €300
    (only the highest band reached applies) — as a **saving** (+);
  - **shipping** — **−€5**, **free** over €100 — as a **cost** (−), or a free-shipping line.
- They're applied to the cart's **discounted active total**; the core sums the lines without
  interpreting them (positive = saving, negative = cost).

### 6) The cart detail page + shared presentation widgets (mini-SDK)

- Clicking a cart opens its **detail page**: the full product table with **preview images**,
  **per-row provenance** and **per-row remove**.
- The product table is now a small set of **shared widgets** (`$lib/components`: thumbnail
  with hover-zoom, category breadcrumb, product cell, tags, discount badge, source chip) —
  one implementation, one look — reused by the **Catalog**, the **cart detail** and the
  **scraper** pages. The Source column is hidden for a single-store cart (one shop) and the
  Photo/Source columns were ordered to match.

### 7) TP Scraper — a test-data generator (dev)

- The throwaway **TP Scraper** plugin page gains an **Add TP product** button (with a
  currency picker) that drops a random fake product — named `TP - …` — into your catalog,
  plus **Remove** and **Clear all**. It gives a **second product source** so **cross-store
  carts**, **delisting** and the **currency-mismatch** rule can be exercised by hand without
  a second real shop.
- It re-delivers your full set through the sanctioned **Catalog Update Service** on every
  add/remove/clear (so a removal *delists* rather than hard-deletes), and it deliberately
  **stays non-schedulable** — no `run_for_user`, so it never shows up in the schedule editor
  or the worker.

### 8) Closing fixes

- **Cart adjustment labels no longer show raw keys.** Every mounted plugin's i18n dictionary
  is now registered **eagerly at startup** (during plugin discovery), not only when its page
  is first opened — so plugin-owned strings consumed by **core** routes (like the Dragon
  Store adjustment labels in a cart) always resolve.
- **Catalog — tighter category breadcrumb.** The category path no longer carries an unwanted
  gap around each `/` separator (`Giochi di Ruolo / GDR Italiano` → `Giochi di Ruolo/GDR
  Italiano`), matching the compact look the Dragon Store page already had.

### 9) Release images also get a `latest` tag (5.T1)

- Each release now publishes both `watch-em-all` and `watch-em-all-ops` as `:x.y.z` **and**
  `:latest` on GHCR, so a `docker compose pull` can track the newest release without editing
  `WEA_VERSION`. Pinning a version stays the recommended default; `latest` is the quick-try
  convenience.

_Under the hood:_ the carts backend opens the core `carts` / `cart_members` tables and the
`/api/carts` API — create with a fixed `mode`, list, rename, delete, plus membership
add/remove (batch-validated, idempotent). The read-only **Cart Engine** (`src/core/cart_engine.py`,
`evaluate_cart`) is a pure function of the catalog + the cart definition; the web layer
resolves the cart's scraper from `app.state` and passes the bound `get_adjustments` in, so
the core never imports the web (the same pattern as `update_catalog` taking its session).
The `Adjustment` contract carries a full **i18n `id`** and `params` the frontend localizes
(`description` is debug-only); the Dragon Store rules live in the plugin
(`.../dragon_store/backend/adjustments.py`). The threshold is a single `threshold_amount`
column on `carts` (1:1, no separate table). The TP Scraper keeps its own
`plugin_tp_scraper_products` table.

## Good to know

- **Alerts are not in this phase.** A cart's per-cart **alert types** and their **baseline**,
  and the cart **price history**, arrive in later phases (6 / 8). A cart today computes and
  displays its state; it does not yet notify.
- The threshold's **percentage is a UI convenience only** — the backend stores and reasons
  about the **€** value. Once set, the € threshold is **fixed**; it is not recomputed as the
  cart's contents change.
- The catalog does **not** yet steer the selection by cart compatibility (grey-out /
  pre-filter). That **multi-scraper compatibility UX** is deferred to **phase 6 (6.F0)**;
  for now an incompatible add comes back as a clear `422`.
- Use the **TP Scraper** page to create a second product source for testing cross carts,
  delisting and currency mismatches without a second real shop.

## Useful Commands

```bash
docker compose -f compose-dev.yml up -d --build         # db + web + worker + pgweb (DB browser on :8081)
docker compose -f compose-dev.yml down -v               # reset the DB (admin recreated from .env)

# Create a single-store (Dragon Store) cart, then a cross cart (user token required)
#   POST /api/carts  {"name":"Wishlist","mode":"scraper_specific","scraper_id":"dragon_store"}
#   POST /api/carts  {"name":"Camera hunt","mode":"cross"}
# Add products:      POST   /api/carts/{id}/items   {"product_ids":[1,2,3]}
# Set a € threshold: PATCH  /api/carts/{id}         {"threshold_amount":300}
# Clear it:          PATCH  /api/carts/{id}         {"threshold_amount":null}
```

**pgweb** (DB browser) — http://localhost:8081, opens straight on the `watchemall`
database. The new tables to inspect: `carts`, `cart_members`.
