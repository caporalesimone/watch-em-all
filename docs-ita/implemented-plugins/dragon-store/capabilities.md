# Dragon Store — Capabilities

> **Implemented plugin** · Dettaglio tecnico (pseudocodice ammesso). File: `backend/__init__.py`, `plugin.py`, `parser.py`, `sanitizer.py` (+ JSON etichette), `discount.py`, `routes.py`.

## Tabelle del plugin

Create in `initialize()`, idempotenti, naming `plugin_dragon_store_*`:

| Tabella | Contenuto |
|---|---|
| `plugin_dragon_store_watches` | user_id, kind (`product`\|`category`), url, **include_ammaccati** (bool, default `false` — usato solo per `kind=category`), created_at — gli input dell'utente |
| `plugin_dragon_store_config` | soglie sconto `[{min_amount, discount_pct}]`, parametri operativi |

## Flusso di `run_for_user`

```
def run_for_user(context, user_id):
    watches  = load_watches(user_id)
    products = []
    for w in watches where w.kind == "category":
        found = scrape_category(context.http, w.url)         # tutte le pagine
        if not w.include_ammaccati:                          # DRG-R4: filtro PER-CATEGORIA
            found, excluded = partition(found, is_ammaccato) # is_ammaccato: prefisso titolo
            count_excluded(excluded)                         # → products_excluded della run
        products += found
    for w in watches where w.kind == "product":
        if not any(p.external_id == expected_id(w.url) for p in products):
            products += scrape_product(context.http, w.url)  # DRG-R3: categoria vince
            # NESSUN filtro ammaccato qui: input singolo = scelta esplicita (DRG-R7)
    products = dedup_by_external_id(products)
    context.update_catalog(user_id, products)
```

Una richiesta alla volta via `context.http` (politeness imposta dal core); paginazione gestita internamente.

Nota su DRG-R8 (l'inclusione vince): il filtro ammaccati avviene **per-watch, prima del merge** — un prodotto filtrato dalla categoria A ma incluso dalla categoria B (o aggiunto come singolo) sopravvive naturalmente al dedup, senza logica speciale.

> **Fase 3 (MVP)**: si implementa **solo il ramo `kind=product`** (scheda singola via `scrape_product`); categorie, filtro ammaccati e paginazione sono **fase 9**. Il parsing reale della scheda è documentato sotto (§ Scheda prodotto `.gp`).

## Adjustments

```
def get_adjustments(self, cart_total):
    thresholds = sorted(config.discount_thresholds, key=lambda t: t.min_amount)
    best = max((t for t in thresholds if cart_total >= t.min_amount),
               default=None, key=lambda t: t.min_amount)
    out = []
    if best:
        out.append(Adjustment(description=f"Sconto soglia {best.min_amount}€",
                              amount=cart_total * best.discount_pct / 100))
    return out
```

## Identità del prodotto

**Pre-analisi (vedi sotto)**: il sito espone un **ID numerico nativo** per prodotto, presente sia nell'URL della scheda (`...gp.<id>.uw`, es. `gp.35880.uw`) sia nella card di listing (`id="r_35880"`, `data-id="prod_35880"`), oltre a un **codice articolo** (`Cod. art.`, es. `XRDCT21`). Strategia: `identity_seed` restituisce l'**id numerico nativo** (stabile e univoco per costruzione), o `None` se non estraibile in qualche contesto → la base applica il fallback `normalize_url(url)` e l'hashing (SCR-R10); `external_id` non è mai assegnato a mano. Il codice articolo si conserva in `extra` come dato informativo.

## Scheda prodotto (`.gp`): parsing reale (studio ad hoc, giugno 2026)

> Verificato su 5 schede reali (`gp.896`, `36099`, `27006`, `34602`, `30708`): scontata, prezzo pieno, esaurita, **preorder**, edizione limitata, categoria diversa. La scheda è server-rendered come la categoria → HTTP + parsing, niente browser headless.

**DRG-Q7 chiusa**: la scheda `.gp` espone un **JSON-LD `Product`** (oltre a `BreadcrumbList`). È la fonte **primaria** del parsing — robusta e non ambigua: la pagina contiene anche **20-46 prodotti correlati** (card con prezzi propri), quindi un parsing DOM "ingenuo" prenderebbe il prodotto sbagliato. Àncore univoche del prodotto principale: **un solo `<h1>`** e **una sola riga `tr.availability`**; i dati DOM si leggono sempre **scoped alla tabella di dettaglio**, mai con selettori page-wide.

**Encoding**: la pagina dichiara `iso-8859-1` ma è in realtà **`windows-1252`** (il byte `0x80` = `€`); inoltre alcuni testi sono **entità HTML** (`Citt&#224;`→Città), altri byte raw (`più`). Il parser **decodifica `cp1252`** e poi applica **`html.unescape()`** su ogni testo estratto.

**Mappatura `Product`** (fonte per campo):

| Campo | Fonte | Note |
|---|---|---|
| `external_id` | URL → `identity_seed` (id nativo `gp.<id>`) | invariato, vedi § Identità |
| `name` | JSON-LD `name` → **sanitizer del titolo** (sotto) | poi `html.unescape` |
| `price_current` | JSON-LD `offers.price` | punto decimale, già pulito |
| `price_original` | DOM riga **"P. Listino"** (`tr.D1`) della tabella principale | virgola → `Decimal`; == corrente se prezzo pieno (→ sconto 0 lato core) |
| `discount_pct` | — (lasciato `None`) | lo calcola il core (CATSVC) |
| `currency` | JSON-LD `priceCurrency` | EUR |
| `is_available` | JSON-LD `offers.availability` | mappa sotto |
| `image_url` | JSON-LD `image` | URL già assoluto |
| `brand` | `text` = JSON-LD `brand.name`; `link` = DOM `tr.T9 > a[href]` reso assoluto | `link` opzionale (PROD-R6) |
| `product_properties` | sanitizer del titolo + disponibilità | vedi sotto (PROD-R5) |
| `category` | JSON-LD `BreadcrumbList` (`itemListElement` → `name` + `@id` relativo reso assoluto), root → leaf | breadcrumb (PROD-R7), costruito con `add_child` |
| `extra` | JSON-LD | `sku` (codice articolo), `priceValidUntil`, `category` (stringa piatta), `description` |

**Mappa disponibilità** (`schema.org` → `is_available` + tag):

| `offers.availability` | DOM | `is_available` | tag |
|---|---|---|---|
| `InStock` | `span.fullAV` ("Disponibile") | `True` | — |
| `OutOfStock` | `span.noAV` ("Non Disponibile") | `False` | — |
| `PreOrder` | `span.inArrivalAV` ("Prossimamente") | **`True`** (ordinabile) | **"Pre Order"** |
| *altro / sconosciuto* | — | `False` | — (+ log per scoprire il nuovo stato) |

## Sanitizer del titolo e `product_properties`

Il titolo del sito porta a volte **etichette commerciali / di edizione** che non fanno parte del nome del prodotto (es. `OFFERTA RAVEN PRIME - …`, `EDIZIONE LIMITATA - …`). Il sanitizer **è specifico di Dragon Store** (non del core; altri scraper possono non averne):

- una lista di etichette **hardcoded in un JSON del plugin**, caricata all'avvio — popolata nel tempo dal manutentore; rappresenta le `product_properties` **possibili** estraibili dal titolo;
- ad ogni scrape, per ogni etichetta presente nel titolo (match **case-insensitive**): viene **tolta dal titolo** e **aggiunta** ai tag via `add_property` (SCR-R16) nella sua **forma canonica** dal JSON;
- sia l'etichetta sia il **titolo residuo** sono **trimmati** da spazi e simboli in testa/coda (es. `"OFFERTA RAVEN PRIME -  "` → `"OFFERTA RAVEN PRIME"`; il titolo perde il `" - "` iniziale rimasto).

Oltre al sanitizer, lo stato **`PreOrder`** aggiunge il tag **"Pre Order"** (che non viene dal titolo). Tutti i tag finiscono in `product_properties` (PROD-R5); la UI li mostra come elenco. L'elenco delle etichette del JSON è **consultabile dall'admin** (vista read-only; arriva con le pagine admin).

## Route del plugin

Sotto `/api/plugins/dragon-store` ([convenzione](../../api/endpoints.md#rotte-plugin-specific)): `config-schema/{admin|user}`, `admin-config` (GET/PUT), `test` (dry-run), `scrape-now` (POST scrape immediato dell'utente + GET stato cooldown), `watches` (GET/POST/DELETE). Lo `scrape-now` e il suo cooldown sono forniti dalla base `ScraperPlugin` (convenzione del core, non riscritti dal plugin). Tag Swagger: `Plugin: Dragon Store`.

**Watches**: `POST /watches` rifiuta un URL **già presente** per l'utente (`409 duplicate_watch`) e fa uno **scrape one-off** (`_dry_context`, nessuna scrittura sul catalogo) per risolvere subito il titolo, salvando uno **snapshot** del prodotto (titolo, immagine, marca, tag, categoria) sulla riga watch (colonna `snapshot_json`), aggiornato a ogni run schedulata/manuale. La pagina utente mostra perciò le watch come la **preview**: immagine, titolo (link), marca, categoria, colonna tag e tasto Remove — il titolo c'è già all'aggiunta, senza dipendere dal catalogo.

## Pre-analisi del sito (giugno 2026, una pagina di categoria)

> Sopralluogo leggero su `il-richiamo-di-cthulhu.1.1.192.sp.uw?idA=19` (HTML scaricato **senza JavaScript**: ciò che segue è nel markup server-rendered). Uno studio ad hoc completo è previsto prima dell'implementazione (fase 3 del [development flow](../../development-flow/phase-03-catalog-first-scrape.md)).

**Tecnologia**: sito classic ASP (endpoint `ajaxRequests.asp`, comandi via query string `?cmd=...`). La pagina di categoria è **interamente server-rendered**: 45 card prodotto complete di prezzi e disponibilità nell'HTML iniziale. AJAX usato solo per ordinamento/cambio vista (`cmd=searchProd&orderBy=...&cView=...`). **Conseguenza**: per le categorie basta HTTP + parsing HTML, niente browser headless.

**Pattern URL** (riconoscimento del tipo di input):

| Tipo | Pattern | Esempio |
|---|---|---|
| Categoria / listing | `<slug>.<l>.<idA>.<idC>.sp.uw` | `il-richiamo-di-cthulhu.1.19.192.sp.uw` |
| Scheda prodotto | `<slug>.<l>.<idA>.<idC>.gp.<idProdotto>.uw` | `...gp.35880.uw` |

**Anatomia della card di listing** (`div.resultBox.prod`, `id="r_<idProdotto>"`):

| Dato | Dove |
|---|---|
| ID nativo | `id="r_35880"` / `data-id="prod_35880"` / URL `.gp.35880.uw` |
| Codice articolo | `dd.code` (es. `XRDCT21`) |
| Titolo + link | `h2.title > a` |
| Immagine | `a.imageLink > img` (path relativo `files/...`) |
| Marca | `dd.T9 > a` (URL `.br.<id>.uw`) |
| Prezzo listino | `del.grossPriceAmount` (es. `€ 59,99` — barrato, presente solo se scontato) |
| Sconto | `span.sDiscount` (es. `Sconto 25%`) |
| Prezzo corrente | `span.mainPriceAmount` (+ `span.mainPriceCurrency`) — **virgola decimale** |
| Disponibilità | `li.availab > span.fullAV` ("Disponibile") / `span.noAV` ("Non Disponibile") |

**"Ammaccato"**: i prodotti danneggiati sono **schede distinte** (proprio id e codice articolo) con titolo prefissato `AMMACCATO - …` → filtro sul prefisso del titolo.

**Paginazione**: la categoria osservata mostra tutte le 45 card in una pagina, senza marker di paginazione/infinite-scroll nell'HTML → da verificare su categorie più grandi (resta in DRG-Q4).

**JSON-LD**: sulla pagina di categoria solo `BreadcrumbList`; la scheda prodotto (`.gp`) potrebbe esporre un `Product` strutturato — da verificare nello studio ad hoc.

## Punti aperti (aggiornati dopo la pre-analisi)

| ID | Punto | Stato |
|---|---|---|
| DRG-Q1 | Dati nel DOM iniziale vs AJAX | ✅ **chiuso**: confermato anche sulla **scheda prodotto** (server-rendered, JSON-LD `Product` presente) |
| DRG-Q2 | Browser headless necessario? | ✅ **chiuso (provvisorio)**: no — HTTP + parsing HTML sufficiente per le categorie |
| DRG-Q3 | SKU/ID nativo stabile | ✅ **chiuso**: id numerico nativo (`gp.<id>`/`r_<id>`) + codice articolo; vedi § Identità |
| DRG-Q4 | Paginazione delle categorie | 🔶 **ridotto**: la categoria campione è single-page (45 card); verificare categorie grandi |
| DRG-Q5 | Segnalazione "ammaccato" e disponibilità | ✅ **chiuso**: titolo `AMMACCATO - …` (schede dedicate); disponibilità a **3 stati** — `InStock`/`fullAV`, `OutOfStock`/`noAV`, **`PreOrder`/`inArrivalAV`** ("Prossimamente") |
| DRG-Q6 | Spese di spedizione come adjustment | da decidere (regole del negozio da leggere) |
| DRG-Q7 | La scheda prodotto (`.gp`) espone JSON-LD `Product`? | ✅ **chiuso**: **sì** — è la fonte **primaria** del parsing (vedi § Scheda prodotto `.gp`) |

> "Chiuso (provvisorio)" = verificato su una pagina campione: lo studio ad hoc pre-implementazione deve confermarlo su più categorie e sulla scheda prodotto. Se servisse il browser headless, la dipendenza va dichiarata in un gruppo opzionale del `pyproject.toml` unico alla root ([build-system](../../infrastructure/build-system.md)); il vincolo di mono-thread resta.
