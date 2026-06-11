# Contratto — `Product`

> **Layer 4 — Contratto** · Audience: developer, plugin developer · Pseudocodice ammesso. Feature: [scraper-plugin](../../3-features/plugins/scraper-plugin.md).

## Scopo

Il confine tra scraper e core: ogni scraper produce esclusivamente istanze di `Product` (via `update_catalog`); il core non vede altro dello scraping.

## Modello

```python
from pydantic import BaseModel
from decimal import Decimal
from datetime import datetime

class Product(BaseModel):
    plugin_id: str
    external_id: str            # ID STABILE e UNIVOCO nello spazio del plugin (vedi sotto)
    url: str
    name: str
    image_url: str | None       # URL remoto, mai scaricata localmente

    price_current: Decimal      # prezzo scontato/corrente
    price_original: Decimal | None
    # None → il core usa l'ultimo listino noto dallo storico; senza storico, price_current
    discount_pct: Decimal | None
    # None → il core lo calcola da original/current
    currency: str = "EUR"       # ISO 4217; V1 non converte né aggrega valute diverse

    is_available: bool          # deciso dallo SCRAPER (out-of-stock temporaneo)
    scraped_at: datetime
    extra: dict = {}            # dati plugin-specific, persistiti in products.extra_json
```

## Regole del contratto

- **PROD-R1** — Lo scraper non conosce lo storico: passa solo lo stato corrente; la risoluzione dei campi `None` è del core ([catalog-update-service](../core/catalog-update-service.md)).
- **PROD-R2** — Lo scraper restituisce **anche** i non disponibili (`is_available = false`); mai filtrarli.
- **PROD-R3** — La lista consegnata è piatta e **deduplicata su `external_id`**.
- **PROD-R4** — `currency` esiste per non rendere breaking l'arrivo di scraper esteri; la UI rende il simbolo (default €).

## `external_id`: identità del prodotto

Insieme a `plugin_id` e `user_id` forma l'identità nel catalogo (UNIQUE sul DB). Obblighi del contratto: **stabile** tra run (stesso prodotto → sempre lo stesso id; se cambia, il core vede un prodotto nuovo e lo storico si spezza) e **univoco** nello spazio del plugin.

Derivazione (responsabilità del plugin, helper della base):

```python
class ScraperPlugin:
    @staticmethod
    def normalize_url(url: str) -> str:
        # rimuove query/fragment volatili, trailing slash, normalizza il case dell'host
        ...

    @staticmethod
    def stable_id(seed: str) -> str:
        # stringa qualunque → id FISSO di 16 hex (64 bit), deterministico tra processi
        import hashlib
        return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
        # MAI hash() built-in: randomizzata da PYTHONHASHSEED
```

Ordine di preferenza per il seme: **SKU/ID nativo del sito** → `stable_id(normalize_url(url))`. Mai titoli o descrizioni (cambiano → identità rotta).
