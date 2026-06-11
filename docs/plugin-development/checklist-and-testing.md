# Checklist di rilascio e test dei plugin

> Audience: plugin developer. La CI esegue i test di contratto su ogni plugin abilitato ([ci](../infrastructure/ci.md)).

## Test di contratto (forniti dal core, obbligatori)

Il core fornisce una suite riusabile che valida **qualunque** plugin contro il suo contratto. Il tuo plugin la istanzia con una fixture:

```python
# tests/test_contract.py del tuo plugin
from core.testing import ScraperContractSuite   # o NotifierContractSuite

class TestMioScraper(ScraperContractSuite):
    plugin_factory = build_mio_scraper           # istanza + context fake con HTTP registrato
    sample_fixtures = ["fixtures/listing.html", "fixtures/product.html"]
```

### Cosa verifica la suite scraper

| Check | Contratto |
|---|---|
| `external_id` **identico** su due run sugli stessi dati | SCR-R9 |
| `external_id` univoci dentro una consegna | SCR-R9 |
| Gli out-of-stock sono **presenti** con `is_available=False` | SCR-R7 |
| Lista deduplicata con input sovrapposti | SCR-R8 |
| `run_test` non invoca mai `update_catalog` né scrive su tabelle | SCR-R11 |
| Tutto l'I/O di rete passa da `context.http` | CTX-R1 |
| Schemi config validi (`ConfigField`), chiavi uniche | CFG-R1 |
| `get_adjustments` restituisce `list[Adjustment]` coerente (0 ok) | SCR-R13 |
| Manifest valido (campi, path relativi, icona esistente) | manifest-reference |

### Cosa verifica la suite notifier

| Check | Contratto |
|---|---|
| `send` gestisce **entrambi** i `kind` senza errori su payload campione | NOT-R1 |
| L'output formattato contiene prezzi, provenienza e link (sui campioni) | NOT-R7 |
| `send_test` funziona con config minima valida | NOT-R6 |
| Errore permanente → `NotifierDeliveryError` con messaggio non vuoto | NOT-R5 |
| Traduzioni presenti per le lingue del core (it, en) | NOT-R4 |

## Test propri del plugin (raccomandati)

- **Fixture HTML/JSON reali** del sito (salvate, anonimizzate se serve): il parsing si testa offline, senza rete.
- Edge del tuo sito: paginazione all'ultima pagina, prodotto senza prezzo, listino assente, categoria vuota.
- Mai test che colpiscono il sito vero in CI.

## Checklist manuale di rilascio

- [ ] Manifest completo (`api_version` corrente, icona, locales)
- [ ] Dry-run dalla UI: risultati sensati, **nessuna riga scritta** (verifica con Adminer in dev)
- [ ] Pagina utente: selezione → entry negli input; pagina admin: parametri + test funzionante
- [ ] Run completa in dev: prodotti a catalogo, provenienza visibile nel Product Picker
- [ ] Seconda run senza modifiche al sito: **zero** nuovi prodotti, zero variazioni spurie (conferma stabilità `external_id`)
- [ ] (Notifier) test di consegna reale dal Profilo, in entrambe le lingue
- [ ] Route documentate nello Swagger (`tags=["Plugin: …"]`)
- [ ] Doc del plugin creata in `implemented-plugins/` (overview + dettagli specifici del sito/canale)
