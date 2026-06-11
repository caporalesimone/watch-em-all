# Dragon Store — Capabilities

> **Implemented plugin** · Dettaglio tecnico (pseudocodice ammesso). File: `backend/__init__.py`, `plugin.py`, `parser.py`, `discount.py`, `routes.py`.

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

**Pre-analisi (vedi sotto)**: il sito espone un **ID numerico nativo** per prodotto, presente sia nell'URL della scheda (`...gp.<id>.uw`, es. `gp.35880.uw`) sia nella card di listing (`id="r_35880"`, `data-id="prod_35880"`), oltre a un **codice articolo** (`Cod. art.`, es. `XRDCT21`). Strategia: `external_id = <id numerico nativo>` (stabile e univoco per costruzione); il codice articolo si conserva in `extra` come dato informativo. Fallback `stable_id(normalize_url(url))` solo se l'id non fosse estraibile in qualche contesto.

## Route del plugin

Sotto `/api/plugins/dragon-store` ([convenzione](../../api/endpoints.md#rotte-plugin-specific)): `config-schema/{admin|user}`, `admin-config` (GET/PUT), `test` (dry-run), `watches` (GET/POST/DELETE). Tag Swagger: `Plugin: Dragon Store`.

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
| DRG-Q1 | Dati nel DOM iniziale vs AJAX | ✅ **chiuso (provvisorio)**: listing server-rendered con prezzi e disponibilità; da confermare sulla scheda prodotto |
| DRG-Q2 | Browser headless necessario? | ✅ **chiuso (provvisorio)**: no — HTTP + parsing HTML sufficiente per le categorie |
| DRG-Q3 | SKU/ID nativo stabile | ✅ **chiuso**: id numerico nativo (`gp.<id>`/`r_<id>`) + codice articolo; vedi § Identità |
| DRG-Q4 | Paginazione delle categorie | 🔶 **ridotto**: la categoria campione è single-page (45 card); verificare categorie grandi |
| DRG-Q5 | Segnalazione "ammaccato" e out-of-stock | ✅ **chiuso**: titolo `AMMACCATO - …` (schede dedicate); `span.fullAV`/`span.noAV` |
| DRG-Q6 | Spese di spedizione come adjustment | da decidere (regole del negozio da leggere) |
| DRG-Q7 | La scheda prodotto (`.gp`) espone JSON-LD `Product`? (parsing più robusto del DOM) | nuovo — da verificare nello studio ad hoc |

> "Chiuso (provvisorio)" = verificato su una pagina campione: lo studio ad hoc pre-implementazione deve confermarlo su più categorie e sulla scheda prodotto. Se servisse il browser headless, la dipendenza va dichiarata nei `pyproject.toml` dei package `web` e `worker` ([build-system](../../infrastructure/build-system.md)); il vincolo di mono-thread resta.
