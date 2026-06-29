# Dragon Store — Features

> **Implemented plugin** · Dettaglio comportamentale (testo + Mermaid). Contratto generico: [scraper-plugin](../../3-features/plugins/scraper-plugin.md).

## Requisiti specifici del plugin

- **DRG-R1** — Due tipi di input per utente: **URL prodotto singolo** e **URL categoria**.
- **DRG-R2** — Una categoria viene enumerata per intero (tutte le pagine) a ogni run; i prodotti trovati entrano nel catalogo dell'utente.
- **DRG-R3** — In caso di sovrapposizione tra input (prodotto singolo presente anche in una categoria osservata), la **categoria ha priorità** e il prodotto è consegnato una sola volta (dedup su `external_id`).
- **DRG-R4** — Prodotti **"ammaccati"**: ogni **categoria** osservata ha un **selettore "includi ammaccati"**, di default **disattivato** (gli ammaccati sono esclusi e conteggiati in `products_excluded`). L'utente che li vuole può attivarlo **categoria per categoria**. Gli out-of-stock sono sempre inclusi con `is_available=false`.
- **DRG-R7** — Un prodotto ammaccato inserito come **prodotto singolo** è **sempre incluso**: averlo aggiunto esplicitamente è una scelta voluta. La UI lo segnala con un **piccolo avviso in rosso** ("Prodotto in stato AMMACCATO") nell'anteprima dry-run e nella lista degli input.
- **DRG-R8** — In caso di sovrapposizione tra fonti con scelte diverse (es. ammaccato escluso dalla categoria A ma incluso dalla categoria B o aggiunto come singolo), **l'inclusione vince**: il prodotto è consegnato.
- **DRG-R5** — Adjustments (5.B5): sul **totale scontato** del carrello applica **una sola** fascia di sconto (la più alta raggiunta, **non cumulabile**) — default fase-5: `≥100 €→5%`, `≥200 €→10%`, `≥300 €→15%` (voce positiva) — più la **spedizione**: `+5,00 €` (voce negativa), **gratis** se il totale ≥ 100 €. I valori vivono nel plugin (`adjustments.py`); diventeranno editabili dall'admin coi ConfigField (fase 7+/9). Ogni voce porta una chiave i18n (`dragon_store.adjustments.*`) che il frontend localizza.
- **DRG-R6** — Il concetto di categoria resta interno: il core e il Product Picker non lo vedono mai.

## UI utente (pagina del plugin)

Navigazione del negozio per scegliere cosa osservare:

```mermaid
flowchart LR
    IN[Campo URL<br/>prodotto o categoria] --> DRY[Dry-run: anteprima live<br/>tabella condivisa, nessuna scrittura]
    DRY --> OK{Va bene?}
    OK -- sì --> SAVE[Conferma → entry negli input<br/>del plugin per l'utente]
    OK -- no --> IN
    LIST[Elenco degli input attivi<br/>con rimozione] --- SAVE
```

- L'utente incolla un URL (il plugin riconosce da sé se è un prodotto o una categoria, grazie ai pattern URL del sito — vedi [pre-analisi](capabilities.md#pre-analisi-del-sito-giugno-2026-una-pagina-di-categoria)), vede l'anteprima dei prodotti che verrebbero osservati, conferma.
- Se l'URL è una **categoria**, il form di conferma include il toggle **"Includi prodotti ammaccati"** (default: off); l'anteprima riflette la scelta. Il toggle è modificabile in seguito dalla lista degli input.
- Se l'URL è un **prodotto singolo in stato AMMACCATO**, l'anteprima mostra un piccolo **avviso in rosso**: il prodotto viene comunque osservato (scelta esplicita, DRG-R7).
- La lista degli input attivi (con tipo, conteggio prodotti dell'ultima run e — per le categorie — lo stato del toggle ammaccati) è gestibile dalla stessa pagina.

## UI admin (pagina admin del plugin)

| Sezione | Contenuto |
|---|---|
| Soglie di sconto | editor delle coppie `{importo minimo, % sconto}` usate dagli adjustments |
| Parametri operativi | timeout richieste, ritardo di politeness, user-agent |
| Test Scraper | dry-run on-demand su un URL, risultati nella tabella condivisa, nessuna scrittura |

## Esempio di adjustments

Carrello scraper-specific con totale scontato **250 €** (fascia ≥200 → 10%):

| Voce | Chiave i18n | Importo |
|---|---|---|
| Sconto soglia 10% | `dragon_store.adjustments.threshold_discount` | **+25.00** (risparmio) |
| Spedizione gratuita | `dragon_store.adjustments.free_shipping` | **0.00** |
| **Stima finale** | | 250 − 25 = **225.00** |

Sotto i 100 € nessuno sconto e spedizione **−5,00 €** (voce negativa). Lo sconto **non è cumulabile**: si applica solo la fascia più alta raggiunta. La soglia del carrello si confronta con la stima finale (CART-R11): è il prezzo che pagherebbe davvero al checkout di Dragon Store.
