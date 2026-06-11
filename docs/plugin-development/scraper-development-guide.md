# Guida — Sviluppare uno scraper

> Audience: plugin developer. Contratto normativo: [3-features/plugins/scraper-plugin.md](../3-features/plugins/scraper-plugin.md) · Esempio reale: [implemented-plugins](../implemented-plugins/).

## Il contratto da implementare

```python
from core.plugins import ScraperPlugin, PluginContext
from core.contracts import Product, Adjustment, ConfigField

class MioScraper(ScraperPlugin):
    plugin_id    = "mio_scraper"          # == manifest.name (validato)
    display_name = "Mio Scraper"
    base_url     = "https://esempio.example"

    def initialize(self, context: PluginContext) -> None:
        # crea le TUE tabelle se non esistono (idempotente):
        # plugin_mio_scraper_watches (user_id, tipo input, valore...)
        # plugin_mio_scraper_config  (parametri operativi, se servono oltre allo schema admin)
        ...

    def has_user_config(self, context, user_id: int) -> bool:
        # il core ti chiede: "questo utente ti ha configurato?" (serve a scrape-now)
        ...

    def configured_users(self, context) -> list[int]:
        # gli utenti con almeno un input nelle tue tabelle
        ...

    def run_for_user(self, context, user_id: int) -> None:
        # L'UNITÀ DI LAVORO: scrapa per un utente e consegna.
        # Mono-thread, una richiesta alla volta via context.http (la cadenza la impone il core).
        products = self._scrape(context, inputs_of(user_id))
        context.update_catalog(user_id, products)     # UNICA via di scrittura del catalogo

    def run_test(self, context, params: dict | None = None) -> list[Product]:
        # Dry-run: scrape on-demand SENZA alcuna scrittura (né catalogo né input).
        # params arriva dalla tua UI; il risultato è mostrato dalla tabella condivisa.
        ...

    def get_adjustments(self, cart_total: Decimal) -> list[Adjustment]:
        # le regole economiche del tuo sito (sconti a soglia, spedizione); [] se nessuna
        ...

    def delete_user_data(self, context, user_id: int) -> None:
        # PURGE di un account (SCR-R14): elimina TUTTE le righe di user_id dalle
        # tue tabelle, in modo idempotente. Il core cancella i suoi dati solo dopo.
        ...

    def get_admin_config_schema(self) -> list[ConfigField]: ...
    def get_user_config_schema(self)  -> list[ConfigField]: ...
```

Il core fornisce `run()` di default (= loop di `run_for_user` sugli utenti configurati): di norma **non** la sovrascrivi.

## I punti dove si sbaglia davvero

### 1. `external_id` (il più importante)

Stabile tra run, univoco nel tuo spazio. In ordine di preferenza:

```python
# 1) il sito ha uno SKU/ID nativo → usalo
external_id = sku
# 2) altrimenti: hash deterministico dell'URL normalizzato
external_id = self.stable_id(self.normalize_url(product_url))   # 16 hex, SHA-256
```

Mai derivarlo da titolo/descrizione (cambiano → identità rotta → storico spezzato per i tuoi utenti). Se il sito cambia struttura URL, preoccupati: è un breaking change per i tuoi dati.

### 2. Disponibilità ed esclusioni

- Out-of-stock → **includi** il prodotto con `is_available=False`. Mai filtrarlo: il core gestisce l'esclusione dai totali e gli alert "tornato disponibile".
- Stati speciali del sito che i tuoi utenti non vogliono (prodotti danneggiati, usati, ecc.) → escludili **tu**, e contali (finiscono in `products_excluded` del monitoraggio).

### 3. Dedup

Se lo stesso prodotto emerge da più input (un URL singolo + una categoria che lo contiene), consegna **una sola** istanza. Decidi tu la precedenza (tipicamente vince l'input più ricco di dati) e documentala nella doc del tuo plugin.

### 4. Rete

- Solo `context.http`: cadenza (politeness), timeout, retry e **conteggio richieste** sono gestiti lì. Se usi una libreria tua, rompi il monitoraggio e le regole di buona educazione.
- Pagina per pagina, con calma: il tuo job è mono-thread per contratto. Il sistema parallelizza *tra* scraper, mai dentro il tuo.
- Browser headless: lecito se il sito lo richiede (dichiara la dipendenza nei package `web`/`worker`); resta il vincolo di sequenzialità.

## La tua UI

- **Pagina utente** (la tua route): qui l'utente sceglie *cosa osservare*. Sei libero sul come (categorie navigabili, inserimento URL, ricerca) con tre obblighi: design system del core, **dry-run di anteprima** (via la tua route di test, nessuna scrittura), selezione confermata → entry nelle tue tabelle.
- **Pagina admin**: generata dal tuo `get_admin_config_schema()` + bottone **Test Scraper** (tabella condivisa). Qui niente selezione di contenuti: solo parametri.

## Route tipiche del tuo backend

Segui la [convenzione](../api/endpoints.md#rotte-plugin-specific): `config-schema/{admin|user}`, `test` (dry-run), `watches` (CRUD degli input utente). Dichiara `tags=["Plugin: Mio Scraper"]` sulle route: finiscono nello Swagger.

## Schema admin tipico

```python
def get_admin_config_schema(self):
    return [
        ConfigField(key="request_timeout_s", label_key="cfg.timeout", type="number", default=20),
        ConfigField(key="politeness_delay_s", label_key="cfg.delay", type="number", default=1.5),
        # + le regole economiche del sito se configurabili (es. soglie sconto)
    ]
```

## Prima del rilascio

Passa la [checklist](checklist-and-testing.md): stabilità dell'`external_id` su run ripetute, inclusione degli out-of-stock, dedup, dry-run senza scritture, schema config valido, icona presente.
