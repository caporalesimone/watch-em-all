# TO BE FIXED

Running list of issues / polish noted by Simone, to address in a future pass.
New items get appended over time.

## Open

### Scrape-now: make the UI core-provided + rework the popup
- **Reported:** rivedere graficamente il popup dello Scrape now. Se possibile lo Scrape now
  (i **componenti grafici**, non solo il backend) va implementato nel **core**, non nel
  singolo scraper, così ogni plugin non deve reimplementarlo. Il popup deve comparire
  **in alto al centro** (non in basso) e **sopra tutti gli elementi**.
- **Where:** the button + confirm popup currently live in the plugin
  [`src/plugins/scrapers/dragon_store/frontend/PluginRoot.svelte`](src/plugins/scrapers/dragon_store/frontend/PluginRoot.svelte);
  the backend mechanism (cooldown, route) is already core/base.
- **Fix idea:** extract a shared **core frontend component** (a `ScrapeNow` widget the
  plugin host injects — same spirit as the common dry-run results table, SCR-R12) so every
  scraper gets the button + cooldown countdown + confirm popup for free. Render the popup
  through a top-level portal/overlay anchored **top-center**, with a z-index above the app
  shell.

### Swap Adminer → pgweb (dev DB browser), preconfigured & login-less
- **Reported (Simone):** sostituire **Adminer** con **pgweb** come browser DB di sviluppo.
  pgweb va **pre-configurato** (utente `admin` / pass `admin`), avviato **solo in debug**
  (profilo `dev`) e **già connesso** al database `watchemall` senza compilare il form di
  connessione. Sarebbe perfetto **evitare anche il login**.
- **Where (touch points found in review):**
  - [`compose.yml`](compose.yml#L97-L103) and [`compose-dev.yml`](compose-dev.yml#L89-L95):
    the `adminer` service (`image: adminer:4`, `ports: ["8081:8080"]`, `profiles: [dev]`).
  - [`compose-dev.yml:8`](compose-dev.yml#L8) header comment "# also adminer on :8081".
  - [`.devcontainer/devcontainer.json:8`](.devcontainer/devcontainer.json#L8) —
    `forwardPorts: [8080, 8081]` (8081 forwarded for the DB browser; can stay).
  - Docs: [`README.md:98`](README.md#L98); [`docs/updates/phase-02.md:38`](docs/updates/phase-02.md#L38);
    [`docs/updates/phase-03.md:33,37,47`](docs/updates/phase-03.md#L33-L47) (incl. the
    "log in with…" step — pgweb shouldn't need it); deployment
    ([`docs/infrastructure/deployment.md:44,110-112`](docs/infrastructure/deployment.md#L44)
    + [`docs-ita`](docs-ita/infrastructure/deployment.md#L48) :48,119-121,137); dev-container
    ([`docs/infrastructure/dev-container.md:44,55`](docs/infrastructure/dev-container.md#L44)
    + [`docs-ita`](docs-ita/infrastructure/dev-container.md#L42) :42,54,70,86,101);
    [`docs-ita/2-architecture/system-overview.md:18,38`](docs-ita/2-architecture/system-overview.md#L18);
    [`docs-ita/4-capabilities/database/schema.md:86`](docs-ita/4-capabilities/database/schema.md#L86) (DB-R6);
    [`docs-ita/developer-rules/infrastructure/rules.md:7,9`](docs-ita/developer-rules/infrastructure/rules.md#L7)
    (INF-1 pins `adminer:4`; INF-3 "Adminer e simili");
    [`docs-ita/plugin-development/checklist-and-testing.md:55`](docs-ita/plugin-development/checklist-and-testing.md#L55);
    [`docs-ita/development-flow/phase-00-pipeline.md:31`](docs-ita/development-flow/phase-00-pipeline.md#L31),
    [`phase-01-foundations.md:19`](docs-ita/development-flow/phase-01-foundations.md#L19).
  - [`CHANGELOG.md:204`](CHANGELOG.md#L204) — historical released entry, **leave as-is**.
- **.env / .env.example:** today **neither** references adminer (adminer needs no config —
  you pick the DB in its UI). pgweb instead wants a connection: feed it a URL built from the
  existing `POSTGRES_*` — `postgres://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}?sslmode=disable`
  (via `DATABASE_URL`/`--url`; confirm the exact env-var name + pgweb's listen port, likely
  `8081:8081`, against the image at implementation time). Passing the URL makes pgweb open
  straight on `watchemall` and **skip the connection form** → that already removes the
  "login". Do **not** set pgweb's HTTP basic auth (`--auth-*`) since the request is to avoid
  login — keep it locked down via the `dev` profile + never exposing 8081 in prod instead.
  - **Credential note to confirm:** the request says "user admin / pass admin", but the dev
    DB is `POSTGRES_USER=admin` / `POSTGRES_PASSWORD=change`. pgweb connects with the **DB**
    creds, so it'd be `admin/change` unless we also set the dev DB password to `admin`. Decide.
- **Fix idea:** replace the `adminer` service with `sosedoff/pgweb` (pin a tag, INF-1), keep
  `profiles: [dev]` (INF-3) + `depends_on: db`, map `8081`, pass the connection URL. Then
  sweep the doc touch points above (drop the Adminer "log in with…" step, rename to pgweb,
  keep :8081) and update the INF-1 pin + INF-3 wording.

### Catalog: drop the Discount column, show -% under Price; strike List price only when discounted
- **Reported (Simone):** togliere la colonna **Sconto** (Discount) dal catalogo e mostrare lo
  sconto — **esattamente com'è ora**, badge con background verde e testo tipo `-50%` — proprio
  **sotto la cifra della colonna Prezzo** (Price), così appare qualcosa del tipo:

  ```
  9,90
  -50%
  ```

  Inoltre il **List price** (Prezzo pieno) deve essere **barrato solo se esiste un Price
  diverso**, cioè quando il prodotto è effettivamente scontato (oggi è sempre barrato).
- **Where:** [`src/frontend/src/routes/catalog/+page.svelte`](src/frontend/src/routes/catalog/+page.svelte):
  - Discount column header (sortable, `discount_pct`):
    [`+page.svelte:153-155`](src/frontend/src/routes/catalog/+page.svelte#L153-L155) — to remove.
  - Discount cell with the green `-50%` badge:
    [`+page.svelte:268-276`](src/frontend/src/routes/catalog/+page.svelte#L268-L276) — to move
    under the Price cell.
  - List price (`price_original`) cell, **always** `line-through` today:
    [`+page.svelte:264-266`](src/frontend/src/routes/catalog/+page.svelte#L264-L266).
  - Price (`price_current`) cell, target for the badge:
    [`+page.svelte:267`](src/frontend/src/routes/catalog/+page.svelte#L267).
  - i18n key `catalog.colDiscount` ("Discount" / "Sconto"):
    [`en.json:30`](src/frontend/src/i18n/en.json#L30), [`it.json:30`](src/frontend/src/i18n/it.json#L30) —
    becomes unused once the header is gone.
- **Fix idea:**
  - Delete the Discount `<th>` and its `<td>`; move the green badge `<span>` (unchanged
    styling) into the Price `<td>`, stacked **below** `money(item.price_current, …)` (e.g. wrap
    both in a column flex / add a `block` under the price), keeping the existing
    `{#if Number(item.discount_pct) > 0}` guard.
  - Make the List price strikethrough **conditional** on a discount: apply `line-through` only
    when `Number(item.discount_pct) > 0` (i.e. `price_current` differs from `price_original`),
    otherwise render it plain.
  - Note the lost **sort-by-discount** control (the column header was the only entry point for
    `sortBy('discount_pct')`); decide whether that sort key is still needed and drop the now
    unused `catalog.colDiscount` i18n key if not.

## Reminders / to discuss

### A standard set of core-frontend components reused by plugins
- **Reminder (Simone):** ha senso ridiscutere un **set di elementi standard** forniti dal
  **core frontend** e riutilizzati dai plugin? Discuterne su come potrebbe funzionare.
- Candidate shared widgets: buttons (consistent hover/fill), popup/overlay (portal,
  top-center, z above shell), the dry-run results table (already meant to be common,
  SCR-R12), tag/badge chips, brand/category breadcrumb, the **Scrape now** control.
- Possible shape: a small design-system exposed via `$lib`, with the plugin host injecting
  the higher-level widgets (Scrape now, dry-run table) so plugins don't re-implement them
  and the look stays consistent. Ties together the three button/popup items above.

### Rename "product properties" → "tags" + dedicated Catalog column
- **Reported (Simone):** the Catalog should have a **dedicated `tags` column**. For Dragon
  Store, the "title labels" show up there. In dragon_store the JSON may stay
  `title_labels.json` (site-specific source), but in the **core** the concept/logic should
  be called **tags**, and the add method **`add_tags`**.
- **Current naming (what to rename):**
  - field `Product.product_properties: list[str]` (PROD-R5) → **`tags`**.
  - base mechanism `new_properties()` → `ProductProperties` with **`add_property(value)`** /
    `get_properties()` (SCR-R16) → e.g. `add_tag`/`get_tags` (Simone asked for `add_tags`).
  - Catalog: tags are currently shown **under the title** → move to a **dedicated column**.
  - Dragon Store `title_labels.json` / `load_title_labels()` / `sanitize_title()` stay; they
    feed the generic tags via the (renamed) add method.
- **Touch points:** `contracts.py`, `base.py`, `models.py` (`products` column), `catalog.py`,
  `web/schemas.py` (`CatalogItem`), `web/routers/catalog.py`, the dragon_store plugin, the
  frontend (client types, catalog column, watched table), docs. Schema change → DB reset.
