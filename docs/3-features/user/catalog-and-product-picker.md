# Catalog & Product Picker

> **Layer 3 — User feature** · Audience: architects, developers.
>
> English translation of the Italian reference [`docs-ita/3-features/user/catalog-and-product-picker.md`](../../../docs-ita/3-features/user/catalog-and-product-picker.md), limited to what is implemented (DOC-12). Phase 3 ships the read-only catalog view (the per-user, searchable, sortable, paginated table); the cart/Product Picker selection role arrives in a later phase.

## Purpose

The catalog is the set of products extracted by the user's scrapers. The **Product Picker** is the table the user consults it through — and, in a later phase, will use to clean it up and select the products to put into carts. It runs no scraping: it is pure selection over data already in the DB (the live previews live on the individual plugin pages).

## Requirements

- **CAT-R1** — The catalog is per-user: it holds the sum of the products extracted by the scrapers the user has configured.
- **CAT-R2** — Every product always shows its **source** (scraper icon + name), with the name **clickable**, linking to the scraper's page. Essential for cross carts ([use case 2](../../../docs-ita/1-business/use-cases.md)).
- **CAT-R3** — **Unavailable** products stay in the catalog (visual indicator); they are never excluded automatically.
- **CAT-R4** — **Delisted** products (`removed`, absent from the last scrape) stay in the table greyed out, excluded from carts and alerts, until the user cleans them up. If they reappear in a scrape, they become active again.
- **CAT-R5** — The table is **paginated server-side**, sortable (source, title, current price, list price, availability, last update), and **searchable by title** (the API also filters by availability and delisting). On open it populates itself (even right after a scrape, which writes asynchronously): no need to launch the search by hand.
- **CAT-R6** — Cleanup actions: remove delisted, selective removal (delete mode), empty the catalog. All with confirmation; the confirmation **states the consequences** (removal from carts and loss of the price history of the affected products). _(Arrives in a later phase, with the picker's selection/cleanup role.)_
- **CAT-R7** — **Catalog empty-state**: when the catalog is empty the Product Picker offers no scraping actions, but **points to the scraper pages** to configure what to watch and start the first population. **Scrape now** is **per-scraper** and lives on the scraper's page, not here ([scraper-plugin](../plugins/scraper-plugin.md), SCR-R15).
- **CAT-R8** — Deleting a product from the catalog removes it **in cascade** from carts and deletes its price history. _(Arrives in a later phase, together with the cart/picker selection role.)_

## The table

| Column | Content |
|---|---|
| Source | Scraper icon + name; **link to the scraper's page** |
| Photo | Remote image (thumbnail with border); **on hover** (after a short delay, so it doesn't pop up while scrolling) it enlarges (whole, not cropped, with size limits) |
| Title | Product name, **link** to the product page (new tab); below it: **brand** (optional link) and **category** (breadcrumb `text / text / …`, each entry clickable) |
| Tags | The product's **tags** (`tags`), in a **dedicated column** (one chip per tag, e.g. _Limited Edition_, _Pre Order_) |
| List price | List price (or last known), **struck through only when there is a discount** |
| Price | Current price; below the figure, a **`-NN%` badge** when the product is discounted (there is no separate "% discount" column) |
| Availability | Indicator (available / out of stock / delisted) |

> The photo and the title act as links to the product: there is no dedicated "Open" column.

## Flows

```mermaid
flowchart LR
    subgraph "Scraper plugin (site page)"
        CFG[The user chooses<br/>what to watch]
    end
    subgraph "Scheduled scrape"
        RUN[Scraper run] --> CAT[(Per-user<br/>catalog)]
    end
    subgraph "Product Picker (core)"
        TAB[Catalog table] --> SEL[Row selection]
        SEL --> CART[Add to cart]
        TAB --> CLEAN[Cleanup: delisted /<br/>selection / empty]
    end
    CFG -.scraper input.-> RUN
    CAT --> TAB
```

Distinction to keep firm (a frequent source of confusion):

| | Plugin page | Product Picker (core) |
|---|---|---|
| Purpose | Decide **what to watch on the site** | Choose products **already in the catalog** for the carts |
| Data | Live preview from the site (dry-run) | DB |
| Writes | Scraper input (plugin tables) | Cart members |

## "Empty catalog → first population" cycle

```mermaid
sequenceDiagram
    participant U as User
    participant P as Scraper page
    participant W as Web (background)
    participant PP as Product Picker

    U->>P: configure what to watch
    U->>P: "Scrape now" (on the scraper's page)
    P->>W: scrape-now (this scraper, this user)
    W->>W: check per-scraper cooldown + per-scraper lock
    W-->>U: started (background job)
    W->>W: run the scraper for the user
    U->>PP: the catalog populates
```

When the catalog is empty the Product Picker invites the user to configure a scraper and start its first scrape **from its own page**: "Scrape now" is **per-scraper** and lives there ([scraper-plugin](../plugins/scraper-plugin.md), SCR-R15). It exists so the first population doesn't take hours to wait for, but it stays available at any time within the individual scraper's cooldown. Otherwise the catalog refreshes at the normal scheduled scrapes.
