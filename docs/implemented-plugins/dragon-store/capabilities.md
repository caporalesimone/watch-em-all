# Dragon Store — Capabilities

> **Implemented plugin — Dragon Store (scraper)** · Audience: developer.
>
> English translation of the Italian reference [`docs-ita/implemented-plugins/dragon-store/capabilities.md`](../../../docs-ita/implemented-plugins/dragon-store/capabilities.md), limited to what is implemented (DOC-12). It covers the phase-3 internals: the real `.gp` single-product parser via `context.http`, product identity, the availability map, the title sanitizer, the plugin routes and the watch snapshot. Files: `backend/__init__.py`, `plugin.py`, `parser.py`, `sanitizer.py` (+ labels JSON), `discount.py`, `routes.py`.

## Plugin tables

Created in `initialize()`, idempotent, naming `plugin_dragon_store_*`:

| Table | Content |
|---|---|
| `plugin_dragon_store_watches` | user_id, kind (`product`\|`category`), url, **include_ammaccati** (bool, default `false` — used only for `kind=category`), created_at — the user's inputs |
| `plugin_dragon_store_config` | discount thresholds `[{min_amount, discount_pct}]`, operational parameters — *populated once the admin config arrives in a later phase* |

## `run_for_user` flow

```
def run_for_user(context, user_id):
    watches  = load_watches(user_id)
    products = []
    for w in watches where w.kind == "category":
        found = scrape_category(context.http, w.url)         # all pages
        if not w.include_ammaccati:                          # DRG-R4: PER-CATEGORY filter
            found, excluded = partition(found, is_ammaccato) # is_ammaccato: title prefix
            count_excluded(excluded)                         # → run's products_excluded
        products += found
    for w in watches where w.kind == "product":
        if not any(p.external_id == expected_id(w.url) for p in products):
            products += scrape_product(context.http, w.url)  # DRG-R3: category wins
            # NO dented filter here: single input = explicit choice (DRG-R7)
    products = dedup_by_external_id(products)
    context.update_catalog(user_id, products)
```

One request at a time via `context.http` (politeness enforced by the core); pagination handled internally.

Note on DRG-R8 (inclusion wins): the dented filter runs **per-watch, before the merge** — a product filtered out of category A but included from category B (or added as a single product) survives the dedup naturally, with no special logic.

> **Phase 3 (MVP)**: only the **`kind=product` branch** is implemented (single `.gp` listing via `scrape_product`); categories, the dented filter and pagination are **phase 9**. The real parsing of the product page is documented below (§ Product page `.gp`).

## Adjustments

*Adjustments arrive in a later phase, together with the admin discount-threshold config.*

```
def get_adjustments(self, cart_total):
    thresholds = sorted(config.discount_thresholds, key=lambda t: t.min_amount)
    best = max((t for t in thresholds if cart_total >= t.min_amount),
               default=None, key=lambda t: t.min_amount)
    out = []
    if best:
        out.append(Adjustment(description=f"Threshold discount {best.min_amount}€",
                              amount=cart_total * best.discount_pct / 100))
    return out
```

## Product identity

**Pre-analysis (see below)**: the site exposes a **native numeric ID** per product, present both in the listing URL (`...gp.<id>.uw`, e.g. `gp.35880.uw`) and in the listing card (`id="r_35880"`, `data-id="prod_35880"`), as well as an **article code** (`Cod. art.`, e.g. `XRDCT21`). Strategy: `identity_seed` returns the **native numeric ID** (stable and unique by construction), or `None` if not extractable in some context → the base applies the `normalize_url(url)` fallback and hashing (SCR-R10); `external_id` is never assigned by hand. The article code is kept in `extra` as informational data.

## Product page (`.gp`): real parsing (ad-hoc study, June 2026)

> Verified on 5 real pages (`gp.896`, `36099`, `27006`, `34602`, `30708`): discounted, full price, sold out, **preorder**, limited edition, different category. The page is server-rendered like the category → HTTP + parsing, no headless browser.

**DRG-Q7 closed**: the `.gp` page exposes a **JSON-LD `Product`** (besides `BreadcrumbList`). It is the **primary** source of the parsing — robust and unambiguous: the page also contains **20-46 related products** (cards with their own prices), so a naive DOM parse would pick the wrong product. Unique anchors for the main product: **a single `<h1>`** and **a single `tr.availability` row**; the DOM data is always read **scoped to the detail table**, never with page-wide selectors.

**Encoding**: the page declares `iso-8859-1` but is actually **`windows-1252`** (the byte `0x80` = `€`); moreover some text is **HTML entities** (`Citt&#224;`→Città), other bytes are raw (`più`). The parser **decodes `cp1252`** and then applies **`html.unescape()`** to every extracted text.

**`Product` mapping** (source per field):

| Field | Source | Notes |
|---|---|---|
| `external_id` | URL → `identity_seed` (native id `gp.<id>`) | unchanged, see § Identity |
| `name` | JSON-LD `name` → **title sanitizer** (below) | then `html.unescape` |
| `price_current` | JSON-LD `offers.price` | decimal point, already clean |
| `price_original` | DOM **"P. Listino"** row (`tr.D1`) of the main table | comma → `Decimal`; == current if full price (→ discount 0 on the core side) |
| `discount_pct` | — (left `None`) | computed by the core (CATSVC) |
| `currency` | JSON-LD `priceCurrency` | EUR |
| `is_available` | JSON-LD `offers.availability` | map below |
| `image_url` | JSON-LD `image` | URL already absolute |
| `brand` | `text` = JSON-LD `brand.name`; `link` = DOM `tr.T9 > a[href]` made absolute | `link` optional (PROD-R6) |
| `tags` | title sanitizer + availability | see below (PROD-R5) |
| `category` | JSON-LD `BreadcrumbList` (`itemListElement` → `name` + relative `@id` made absolute), root → leaf | breadcrumb (PROD-R7), built with `add_child` |
| `extra` | JSON-LD | `sku` (article code), `priceValidUntil`, `category` (flat string), `description` |

**Availability map** (`schema.org` → `is_available` + tag):

| `offers.availability` | DOM | `is_available` | tag |
|---|---|---|---|
| `InStock` | `span.fullAV` ("Disponibile") | `True` | — |
| `OutOfStock` | `span.noAV` ("Non Disponibile") | `False` | — |
| `PreOrder` | `span.inArrivalAV` ("Prossimamente") | **`True`** (orderable) | **"Pre Order"** |
| *other / unknown* | — | `False` | — (+ log to discover the new state) |

## Title sanitizer and `tags`

The site's title sometimes carries **commercial / edition labels** that are not part of the product name (e.g. `OFFERTA RAVEN PRIME - …`, `EDIZIONE LIMITATA - …`). The sanitizer **is specific to Dragon Store** (not the core; other scrapers may not have one):

- a list of labels **hardcoded in a plugin JSON**, loaded at startup — populated over time by the maintainer; it represents the **possible** `tags` extractable from the title;
- on each scrape, for every label present in the title (**case-insensitive** match): it is **removed from the title** and **added** to the tags via `add_tag` (SCR-R16) in its **canonical form** from the JSON;
- both the label and the **residual title** are **trimmed** of leading/trailing spaces and symbols (e.g. `"OFFERTA RAVEN PRIME -  "` → `"OFFERTA RAVEN PRIME"`; the title loses the leftover leading `" - "`).

Besides the sanitizer, the **`PreOrder`** state adds the **"Pre Order"** tag (which does not come from the title). All tags end up in `tags` (PROD-R5); the UI shows them as a list. The list of labels in the JSON is **viewable by the admin** (read-only view; arrives with the admin pages).

## Plugin routes

Under `/api/plugins/dragon-store` ([convention](../../api/endpoints.md)): `config-schema/{admin|user}`, `admin-config` (GET/PUT), `test` (dry-run), `scrape-now` (POST immediate scrape for the user + GET cooldown status), `watches` (GET/POST/DELETE). The `scrape-now` and its cooldown are provided by the `ScraperPlugin` base (core convention, not rewritten by the plugin). Swagger tag: `Plugin: Dragon Store`.

**Watches**: `POST /watches` rejects a URL **already present** for the user (`409 duplicate_watch`) and performs a **one-off scrape** (`_dry_context`, no catalog write) to resolve the title immediately, saving a **snapshot** of the product (title, image, brand, tags, category) on the watch row (column `snapshot_json`), refreshed on every scheduled/manual run. The user page therefore shows the watches as the **preview**: image, title (link), brand, category, tags column and a Remove button — the title is already there at add time, without depending on the catalog.

## Site pre-analysis (June 2026, one category page)

> Light walkthrough on `il-richiamo-di-cthulhu.1.1.192.sp.uw?idA=19` (HTML downloaded **without JavaScript**: what follows is in the server-rendered markup). A full ad-hoc study is planned before implementation (phase 3 of the [development flow](../../../docs-ita/development-flow/phase-03-catalog-first-scrape.md)).

**Technology**: classic ASP site (endpoint `ajaxRequests.asp`, commands via query string `?cmd=...`). The category page is **entirely server-rendered**: 45 product cards complete with prices and availability in the initial HTML. AJAX used only for sorting/view change (`cmd=searchProd&orderBy=...&cView=...`). **Consequence**: for categories, HTTP + HTML parsing is enough, no headless browser.

**URL patterns** (input type recognition):

| Type | Pattern | Example |
|---|---|---|
| Category / listing | `<slug>.<l>.<idA>.<idC>.sp.uw` | `il-richiamo-di-cthulhu.1.19.192.sp.uw` |
| Product page | `<slug>.<l>.<idA>.<idC>.gp.<idProduct>.uw` | `...gp.35880.uw` |

**Listing card anatomy** (`div.resultBox.prod`, `id="r_<idProduct>"`):

| Datum | Where |
|---|---|
| Native ID | `id="r_35880"` / `data-id="prod_35880"` / URL `.gp.35880.uw` |
| Article code | `dd.code` (e.g. `XRDCT21`) |
| Title + link | `h2.title > a` |
| Image | `a.imageLink > img` (relative path `files/...`) |
| Brand | `dd.T9 > a` (URL `.br.<id>.uw`) |
| List price | `del.grossPriceAmount` (e.g. `€ 59,99` — struck through, present only if discounted) |
| Discount | `span.sDiscount` (e.g. `Sconto 25%`) |
| Current price | `span.mainPriceAmount` (+ `span.mainPriceCurrency`) — **decimal comma** |
| Availability | `li.availab > span.fullAV` ("Disponibile") / `span.noAV` ("Non Disponibile") |

**"Dented"**: damaged products are **separate listings** (own id and article code) with a title prefixed `AMMACCATO - …` → filter on the title prefix. *The dented filter arrives in phase 9.*

**Pagination**: the observed category shows all 45 cards on one page, with no pagination/infinite-scroll marker in the HTML → to be verified on larger categories (remains in DRG-Q4). *Pagination arrives in phase 9.*

**JSON-LD**: on the category page only `BreadcrumbList`; the product page (`.gp`) might expose a structured `Product` — to be verified in the ad-hoc study (since confirmed: see § Product page `.gp`).

## Open points (updated after the pre-analysis)

| ID | Point | Status |
|---|---|---|
| DRG-Q1 | Data in the initial DOM vs AJAX | ✅ **closed**: confirmed on the **product page** too (server-rendered, JSON-LD `Product` present) |
| DRG-Q2 | Headless browser needed? | ✅ **closed (provisional)**: no — HTTP + HTML parsing is enough for categories |
| DRG-Q3 | Stable SKU/native ID | ✅ **closed**: native numeric id (`gp.<id>`/`r_<id>`) + article code; see § Identity |
| DRG-Q4 | Category pagination | 🔶 **reduced**: the sample category is single-page (45 cards); verify large categories |
| DRG-Q5 | "Dented" flagging and availability | ✅ **closed**: title `AMMACCATO - …` (dedicated listings); **3-state** availability — `InStock`/`fullAV`, `OutOfStock`/`noAV`, **`PreOrder`/`inArrivalAV`** ("Prossimamente") |
| DRG-Q6 | Shipping costs as an adjustment | to be decided (store rules to be read) |
| DRG-Q7 | Does the product page (`.gp`) expose JSON-LD `Product`? | ✅ **closed**: **yes** — it is the **primary** source of the parsing (see § Product page `.gp`) |

> "Closed (provisional)" = verified on one sample page: the pre-implementation ad-hoc study must confirm it across multiple categories and on the product page. Should a headless browser be needed, the dependency must be declared in an optional group of the single root `pyproject.toml` ([build-system](../../infrastructure/build-system.md)); the single-thread constraint remains.
