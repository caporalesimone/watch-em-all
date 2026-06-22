# TO BE FIXED

Running list of issues / polish noted by Simone, to address in a future pass.
New items get appended over time.

## Open

### Catalog page "blinks" when empty
- **Reported:** blink nella pagina del catalog se è vuoto.
- **Likely cause:** the empty-state auto-retry added for the post-scrape race in
  [`src/frontend/src/routes/catalog/+page.svelte`](src/frontend/src/routes/catalog/+page.svelte)
  (`onMount`) re-runs `load()` every ~1.5s while `total === 0`, and `load()` flips
  `loading = true` each time → the "Loading…" ⇄ empty-state swap reads as a blink
  (up to 4 retries).
- **Fix idea:** don't toggle the full `loading` flag on the background retries (only on
  the first/explicit load), or stop once a genuine empty result is confirmed, or poll
  silently without re-rendering the loading branch.

### Watched-list product image is oversized
- **Reported:** l'immagine nella watch list è gigante; va forzata la dimensione, stessa
  altezza della riga di preview.
- **Where:** watched table in
  [`src/plugins/scrapers/dragon_store/frontend/PluginRoot.svelte`](src/plugins/scrapers/dragon_store/frontend/PluginRoot.svelte)
  (watched image is currently `h-12 w-12`; the dry-run **preview** row image is `h-10 w-10`).
- **Fix idea:** force the watched image to a fixed size matching the preview row
  (`h-10 w-10`, `object-cover`), and make sure the size constraint actually applies (the
  class isn't being overridden / is included in the build).

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

### Scrape-now still doesn't read as a button
- **Reported:** Scrape now ancora non risulta essere come un bottone.
- **Note:** the previous attempt (outlined emerald that fills on hover) didn't land —
  needs a clearer button affordance. Best solved together with the core-provided
  `ScrapeNow` component above.

### Remove button has no hover-fill (unlike the Preview button)
- **Reported:** il tasto Remove non ha un effetto grafico di riempimento sull'hover come
  fa Preview.
- **Where:** watched table Remove button in
  [`src/plugins/scrapers/dragon_store/frontend/PluginRoot.svelte`](src/plugins/scrapers/dragon_store/frontend/PluginRoot.svelte)
  (currently `hover:bg-red-50` — too subtle / not landing).
- **Fix idea:** give it the same visible fill-on-hover treatment as the Preview button.

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
