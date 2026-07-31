# Dragon Store — Capabilities

> **Implemented plugin — Dragon Store (scraper)** · Audience: developer.
>
> Limited to what is implemented (DOC-12). It covers the internals: the `.gp` product parser and the `.sp` listing walk via `context.http`, product identity, the availability map, the title sanitizer, the cart adjustments, the plugin tables (the watch row that doubles as a job) and the plugin routes. Files: `backend/__init__.py` (plugin class + routes), `adjustments.py`, `parser.py`, `sanitizer.py` (+ `title_labels.json`).

## Plugin tables

Created in `initialize()`, idempotent, naming `plugin_dragon_store_*`:

| Table | Content |
|---|---|
| `plugin_dragon_store_watches` | id, user_id, kind (`product`\|`category`), url, **snapshot_json** (display snapshot: for a product its name/image/brand/tags/category, for a category its breadcrumb — null until the first successful scrape), created_at, **include_ammaccati**, **status** + status_detail + progress_done + progress_total + cancel_requested + queued_at/started_at/finished_at, **products_included** + products_excluded + last_scanned_at — **UNIQUE (user_id, url)** |

Three groups of columns, three jobs:

- **The input**: `kind` and `url`. A category stays **one row** — the run re-scrapes the category, never the hundred products that came out of it, and the products carry no link back here (one product can arrive from several watches at once).
- **The job** (`status` and its neighbours): the row **is** the job that resolves it. Adding a watch commits this row first and scrapes afterwards, so the state describing a two-minute (or, for a category, several-minute) wait lives where a page reload can find it again instead of in a component a refresh throws away. `queued → running → ready | failed | cancelled`; `progress_*` counts **requests**, which is where the time goes. `cancel_requested` is cooperative: a thread cannot be killed, and does not need to be.
- **The last scan** (`products_included`, `products_excluded`, `last_scanned_at`): a photograph the UI reads, not a live count — see the note on the absent foreign key above.

The `UNIQUE (user_id, url)` is the duplicate guarantee. It used to be a `SELECT` before an `INSERT` with a two-minute scrape in between, which is a race with a window that wide, not a guarantee: two quick submissions of the same URL wrote two rows.

There is **no config table yet**: the adjustment values live in code (`adjustments.py`); the admin discount-threshold editor (and its persistence) arrives with the plugin admin config in a later phase.

## `run_for_user` flow

```
def run_for_user(context, user_id):
    watches = load_watches(user_id)
    if not watches:
        return DeltaCounters()          # no watches != "the site returned nothing": NEVER delist
    delivered, unpriced, excluded, failed = {}, [], 0, 0

    for w in categories(watches):                            # 1. categories FIRST
        found = scrape_category(context.http, w)             # walks &pg=N, page 1 states the count
        #   the dented filter reads the SANITISER's tag, never a second search of the title
        #   (DRG-R4, per-category): the label is stripped from the name, so a detector running
        #   after it would find nothing and one running before would be the rule written twice
        excluded += found.excluded                           # → DeltaCounters.excluded → scrape_run
        record_scan(w, found)                                # counters + breadcrumb on the row
        delivered.update(found.products); unpriced += found.unpriced
        failed += 0 if found.complete else 1

    for w in singles(watches):                               # 2. then the singles
        if expected_id(w.url) in delivered:
            continue                                         # DRG-R3: the category already did it
        delivered[...] = scrape_product(context.http, w.url)  # no dented filter here (DRG-R7)

    resolve_unpriced(unpriced, delivered)                    # 3. last: 9.B2b, detail page each

    if not aborted and failed == 0:
        return context.update_catalog(user_id, delivered)     # complete → may delist
    return context.upsert_catalog(user_id, delivered)         # partial → must NOT delist
```

Categories first is not cosmetic (9.B4): a card yields the same `external_id` as the detail page, so a product a category already delivered needs **no request of its own** — five single watches covered by one category go from 77 seconds to 22. One request at a time via `context.http` (politeness enforced by the core).

The last two lines are the phase's most consequential rule (CATSVC-R2/R2b): a page that could not be read makes the delivery **incomplete**, and an incomplete delivery must never run the delisting sweep. "We could not read page 7" is not "those products are gone" — that confusion is what used to wipe a catalog on any gate or outage.

Note on DRG-R8 (inclusion wins): the dented filter runs **per-watch, before the merge** — a product filtered out of category A but included from category B (or added as a single product) survives the dedup naturally, with no special logic.

**Idempotency**: with the site unchanged, a second (and third) run over the same category delivers the same set and reports **every delta at zero**, `removed` included — which matters most there, since a complete delivery is precisely the one *allowed* to delist.

## Adjustments (5.B5)

Implemented in `adjustments.py` as a small rules class (`DragonAdjustments`), applied to a scraper_specific cart's **discounted total**. Each rule yields a signed `Adjustment` (positive = saving, negative = cost) carrying the **full i18n key** the frontend localizes (`id`) and its interpolation `params`; `description` is debug-only. The core sums them. The phase-5 values live in code (admin-editable later).

- **Threshold discount** (`dragon_store.adjustments.threshold_discount`): a **non-cumulative** band — only the highest whose minimum is reached applies. Bands: `≥100 €→5%`, `≥200 €→10%`, `≥300 €→15%`. Below 100 € there is no discount.
- **Shipping**: `dragon_store.adjustments.free_shipping` (amount `0.00`) when the total ≥ 100 €, else `dragon_store.adjustments.shipping` with amount `−5.00 €`.

```
class DragonAdjustments:
    discount_bands = ((100, 5), (200, 10), (300, 15))   # (min discounted total, percent)
    shipping_cost = 5.00
    free_shipping_min = 100

    def compute(self, cart_total):
        out = []
        pct = highest_band_reached(self.discount_bands, cart_total)   # 0 below the first minimum
        if pct > 0:
            out.append(Adjustment(id="dragon_store.adjustments.threshold_discount",
                                   amount=round(cart_total * pct / 100, 2),   # positive → saving
                                   params={"pct": pct}))
        if cart_total >= self.free_shipping_min:
            out.append(Adjustment(id="dragon_store.adjustments.free_shipping", amount=0.00))
        else:
            out.append(Adjustment(id="dragon_store.adjustments.shipping",
                                   amount=-self.shipping_cost, params={"cost": self.shipping_cost}))
        return out
```

The plugin's `get_adjustments(self, products, cart_total)` delegates to `ADJUSTMENTS.compute(cart_total)`.

## Product identity

**Pre-analysis (see below)**: the site exposes a **native numeric ID** per product, present both in the listing URL (`...gp.<id>.uw`, e.g. `gp.35880.uw`) and in the listing card (`id="r_35880"`, `data-id="prod_35880"`), as well as an **article code** (`Cod. art.`, e.g. `XRDCT21`). Strategy: `identity_seed` returns the **native numeric ID** (stable and unique by construction), or `None` if not extractable in some context → the base applies the `normalize_url(url)` fallback and hashing (SCR-R10); `external_id` is never assigned by hand. The article code is kept in `extra` as informational data.

## Anti-bot interstitial and rate limiting (site change, 25 July 2026)

The site started answering the **first request of every session** with a "Verifica accesso / Security Check" page — a fake-Cloudflare "I am not a robot" checkbox, served with **HTTP 200** and roughly 13,200 bytes. The status code therefore carries no information and the body is the only evidence: the parser classifies it before looking for the JSON-LD (`DragonStoreChallenge`), because reporting `no JSON-LD Product` for it was true and useless.

Their error pages behave the same way: a `<div id="pageNotFound">` carrying the real status inside a `200` body (`DragonStoreRateLimited` for 429, `DragonStoreSoftError` otherwise).

**What the site actually permits.** `robots.txt` publishes `User-agent: *` and `Crawl-delay: 10`, with **no `Disallow`** — crawling these pages is allowed, and the only condition is the rate. We had been leaving 1.5 s between requests, and retries went out after 0.5 s: about seven times faster than asked, which is the likely cause of the `429` the site began returning. The core client now enforces both directives (CTX-R10), which was the real fix.

**Getting past the gate.** The interstitial's checkbox clears the session with a single `GET /ajaxRequests.asp?cmd=captcha_check_ok` (header `ReadyAjaxAuth: readypro`, answer `OK`); the cleared flag then lives in the `ASPSESSIONID*` cookie, which is why the client keeps a cookie jar for the whole run. Done once per run, this is *fewer* requests than before, when every page fetched an interstitial and retried for nothing. Verified end-to-end on 26 July 2026 with our own User-Agent and the 10 s delay: 13,200-byte gate → `OK` → the real 135,781-byte page with its `"@type":"Product"`.

Two lines we do not cross: we identify ourselves honestly (no browser impersonation — if Dragon Store does not want us, a `Disallow` in `robots.txt` is the clean instruction and it will be obeyed), and a rate limit **aborts the whole run** rather than pressing on.

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

> **Anchoring (done in 0.9.0).** The match used to be made **anywhere** in the title. Counted over 139 real cards, all 28 label occurrences — `AMMACCATO` (13), `OFFERTA RAVEN PRIME` (9), `EDIZIONE LIMITATA` (3) — sit at the **start**; none is internal, none trails. It is now anchored to the **start or the end** of what is left of the title (leading separators a previous removal left behind still count as an edge), which loses nothing on real data and removes the one defect the free-form match carried: cutting a label out of the middle leaves a ` - - ` residue behind, since separator trimming only applies at the ends — and a product whose *name* contains a label word is no longer mutilated.

## Plugin routes

Under `/api/plugins/dragon-store` ([convention](../../api/endpoints.md)), the plugin's own router implements `classify` (`GET ?url=` → the kind, for the add form), `watches` (`GET` list, `POST` add → 201, `PATCH /watches/{id}` for the dented filter, `POST /watches/{id}/cancel`, `DELETE /watches/{id}`) and `watches/job` (`GET`, the in-flight add). A `test` route (dry-run) existed until 0.9.0 and was removed with the concept. The `scrape-now` pair (`POST` immediate scrape for the user + `GET` cooldown status) is provided by the `ScraperPlugin` base (core convention, not rewritten by the plugin) and since 0.9.0 answers **403** below super-user. The `config-schema/{admin|user}` and `admin-config` (GET/PUT) convention routes are **not implemented yet** — they arrive with the plugin admin config in a later phase. Swagger tag: `Plugin: Dragon Store`. Full signatures and error codes: [endpoints](../../api/endpoints.md#scraper-plugin-routes--dragon-store-implemented).

**Watches**: `POST /watches` **commits the row and returns in milliseconds**, then resolves it outside the request — the row *is* the job (see § Plugin tables). It used to be the other way round, with the wait (the site's `Crawl-delay` plus its access check, up to a couple of minutes) inside the request and everything describing it living in the page: a reload wiped the spinner but not the scrape, so the work finished and wrote invisibly, and the user, seeing nothing, added the same URL again. Refusals are the API's, not a disabled button's: a duplicate URL → `409 duplicate_watch` (the UNIQUE), another add already in flight → `409 add_in_progress`, an unrecognised URL → `422 invalid_url`.

The queue is drained by **this scraper's own drainer**, which holds the same per-scraper run lock as a scheduled run (so an add never competes with one) and takes the oldest queued job at a time. A row still marked `running` at startup cannot be — that is what a restart left behind — so it is reclaimed as `failed`; leaving it would block the user's next submission, a lock with no expiry.

Resolution writes through `upsert_catalog` — never `update_catalog`, since one input says nothing about the user's other products — and refreshes the watch's `snapshot_json`. The watch is **kept even when the scrape fails**: "we could not read it" is not "it is not there", and the next scheduled run tries again.

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
| Availability | `li.availab > span.fullAV` ("Disponibile") / `span.noAV` ("Non Disponibile") / **`span.inArrivalAV`** ("Prossimamente") — all three states appear on cards |
| Short description | `p.description` — a one-line abstract, **not** the full description of the detail page |
| Badges | `div.product-badges > span.badge-ribbon-title b2|b3` — empty CSS ribbons, also present on the detail page; meaning unknown, unused |

Verified on 139 cards (2026-07-29): everything the catalog row needs is on the card, and the card's native id yields the **same `external_id`** as the product page. Only `priceValidUntil`, the long description and the detail-page image are missing — none of which any page of the app renders.

**Cards with no price at all** (2-4% of the sample) omit the whole `li.price` block *and* the cart form. Two different situations look **identical on the card** and are told apart only by availability: a free digital download (available, and its detail page has no price either), and a product withheld from sale (`noAV`, whose detail page still carries a `P. Listino` row — `L'Isola Proibita`, 24,95 €, is one). *Their handling arrives in phase 9.*

**"Dented"**: damaged products are **separate listings** (own id and article code) whose title starts with the label, in both the `AMMACCATO - ` and `AMMACCATO-` forms. Detection is the **title sanitizer's tag**, not a second search on the title (see § Title sanitizer). The word also occurs in some *descriptions*, which are deliberately not inspected. *The dented filter arrives in phase 9.*

**Pagination** *(settled 2026-07-29 on a real 1040-product category, `classici-famiglia.1.1.115.sp.uw?idA=16`)*: page size is **50**, and both above and below the list the page states `1040 risultati trovati (50 per pagina - 21 in totale)` — the item count **and the page count**. Page links are ordinary `<a href>` with **`&pg=N`** (plus a `class="next"` link); `&pg=2` was fetched and returns 50 cards with **zero overlap** with page 1. No AJAX, no headless browser. Two consequences: the total is known from the **first** request, and a category costs `ceil(products / 50)` requests — a 100-product category is **2** requests, while a single-product watch costs 1 request *per product*. *Pagination arrives in phase 9.*

**JSON-LD**: on the category page only `BreadcrumbList`; the product page (`.gp`) might expose a structured `Product` — to be verified in the ad-hoc study (since confirmed: see § Product page `.gp`).

## Open points (updated after the pre-analysis)

| ID | Point | Status |
|---|---|---|
| DRG-Q1 | Data in the initial DOM vs AJAX | ✅ **closed**: confirmed on the **product page** too (server-rendered, JSON-LD `Product` present) |
| DRG-Q2 | Headless browser needed? | ✅ **closed (provisional)**: no — HTTP + HTML parsing is enough for categories |
| DRG-Q3 | Stable SKU/native ID | ✅ **closed**: native numeric id (`gp.<id>`/`r_<id>`) + article code; see § Identity |
| DRG-Q4 | Category pagination | ✅ **closed** (2026-07-29): server-rendered `&pg=N` links, 50 per page, item and page counts printed on every page; verified on a 1040-product category |
| DRG-Q5 | "Dented" flagging and availability | ✅ **closed**: title `AMMACCATO - …` (dedicated listings); **3-state** availability — `InStock`/`fullAV`, `OutOfStock`/`noAV`, **`PreOrder`/`inArrivalAV`** ("Prossimamente") |
| DRG-Q6 | Shipping costs as an adjustment | ✅ **closed** (2026-07-30): shipping **is** an adjustment and has been implemented since phase 5 — `adjustments.py` yields **−5.00 €** as a NEGATIVE entry, **free** from 100 € up, alongside the non-cumulative discount band. The question was answered by the code before it was answered in this table; nothing was left to decide |
| DRG-Q7 | Does the product page (`.gp`) expose JSON-LD `Product`? | ✅ **closed**: **yes** — it is the **primary** source of the parsing (see § Product page `.gp`) |

> "Closed (provisional)" = verified on one sample page: the pre-implementation ad-hoc study must confirm it across multiple categories and on the product page. Should a headless browser be needed, the dependency must be declared in an optional group of the single root `pyproject.toml` ([build-system](../../infrastructure/build-system.md)); the single-thread constraint remains.
