# Scraper Plugin (contratto generico)

> **Layer 3 — Feature plugin** · Audience: architetti, plugin developer · Testo + Mermaid, niente codice. Contratto tecnico: [4-capabilities/contracts/product.md](../../4-capabilities/contracts/product.md) · Guida pratica: [plugin-development/scraper-development-guide.md](../../plugin-development/scraper-development-guide.md).

Questo documento descrive **lo scraper astratto**: tutto ciò che ogni scraper è e deve fare, indipendentemente dal sito. Nessun riferimento a siti reali — i plugin concreti sono documentati in [implemented-plugins/](../../implemented-plugins/).

## Cos'è uno scraper

Un produttore **stateless** e **internamente mono-thread** di prodotti: legge i propri input (cosa osservare, per quale utente), visita il sito con calma — una richiesta alla volta, cadenzata — e consegna al core la lista corrente dei prodotti trovati. Tutto ciò che riguarda il sito (struttura, navigazione, categorie, paginazione, stati speciali dei prodotti) è **interno al plugin**: il core non ne sa nulla.

## Responsabilità: scraper vs core

| Responsabilità | Scraper | Core |
|---|---|---|
| Sapere cosa osservare per ogni utente (input propri) | ✅ | — |
| Strategia di scraping (DOM, chiamate interne, browser) | ✅ | — |
| Concetto di categoria, paginazione, filtri del sito | ✅ | — |
| Identità stabile del prodotto (`external_id`) | ✅ (garantirla) | usa |
| Decidere la disponibilità (`is_available`) | ✅ | — |
| Esclusioni specifiche del sito (stati speciali del prodotto) | ✅ | — |
| Calcolo adjustments del carrello (regole del sito) | ✅ | applica |
| Storico, delta, delisting | — | ✅ |
| Scrittura nel catalogo | — | ✅ (unica via: callback) |
| Quando girare, parallelismo, politeness, timeout | — | ✅ |

## Requisiti del contratto

### Input e configurazione
- **SCR-R1** — Lo scraper possiede i **propri input** in tabelle dedicate (namespaced per plugin), per utente, che crea da sé se non esistono. Ogni configurazione utente (dalla pagina del plugin) crea una o più entry.
- **SCR-R2** — Configurazione a due livelli come ogni plugin: **admin** (parametri operativi: timeout, identificazione, politeness, regole del sito) e **utente** (cosa osservare). Entrambe descritte da schemi dichiarativi per i form dinamici.
- **SCR-R3** — Lo scraper sa rispondere al core se un utente lo ha configurato (serve per lo scrape-now: il core non legge le tabelle del plugin).

### Esecuzione
- **SCR-R4** — L'unità di esecuzione è **per utente**: il core invoca lo scraper per ciascun utente configurato; la run schedulata itera tutti gli utenti, lo scrape-now uno solo. Lo scraper non decide mai *quando* girare.
- **SCR-R5** — Lo scraper è **stateless**: produce solo lo stato corrente, non conosce lo storico né i delta (mestiere del core).
- **SCR-R6** — Lo scraper è **internamente mono-thread**: nessun parallelismo interno verso il sito. Usa **esclusivamente il client HTTP fornito dal contesto**, che impone il ritmo (politeness) e conta le richieste per il monitoraggio.
- **SCR-R7** — Restituisce **anche i prodotti non disponibili** (marcati); non li filtra mai. Le esclusioni specifiche del sito (es. prodotti in stati speciali che l'utente non vuole) avvengono dentro il plugin, e i prodotti esclusi sono conteggiati per il monitoraggio.
- **SCR-R8** — La lista consegnata è **piatta e deduplicata** sull'identità: se lo stesso prodotto emerge da più input (es. input singolo + categoria che lo contiene), compare una volta sola.

### Identità del prodotto (il punto più delicato)
- **SCR-R9** — Ogni prodotto porta un **`external_id` stabile tra run e univoco** nello spazio del plugin. È l'aggancio di tutto: riconoscimento, storico, disponibilità, delisting. Se cambia, il core vede un prodotto nuovo e lo storico si spezza.
- **SCR-R10** — Derivazione raccomandata, in ordine: l'**identificativo nativo** del sito (SKU/ID prodotto) se esiste; altrimenti un **hash deterministico dell'URL normalizzato** (il core fornisce gli helper). Mai usare titoli o descrizioni come seme: cambiano.

### Dry-run / Test
- **SCR-R11** — Ogni scraper implementa una funzione di **test**: uno scrape on-demand che restituisce i prodotti trovati **senza scrivere nulla** (né catalogo né input). Parametrizzata dall'input raccolto dalla UI del plugin.
- **SCR-R12** — La visualizzazione dei risultati del test è **comune** (componente tabella del design system alimentato dal risultato): il plugin non reimplementa la tabella. Il dry-run serve sia all'utente (anteprima di cosa osserverà) sia all'admin (verifica di funzionamento dalla pagina admin del plugin).

### Adjustments
- **SCR-R13** — Lo scraper espone il calcolo degli **adjustments** per i carrelli a lui legati: dato il totale, restituisce le voci correttive secondo le regole del sito (sconti a soglia, spedizione). Il core le applica senza conoscerne la logica. Contratto: [adjustment](../../4-capabilities/contracts/adjustment.md).

## Flusso di una run (vista contrattuale)

```mermaid
sequenceDiagram
    participant POOL as Pool (core)
    participant S as Scraper
    participant SITE as Sito
    participant CAT as Catalog Update (core)

    POOL->>S: esegui per utente U
    S->>S: leggi input di U (tabelle proprie)
    loop per ogni input, una richiesta alla volta
        S->>SITE: richiesta (via http del contesto, cadenzata)
        SITE-->>S: pagina/dati
        S->>S: estrai, normalizza, assegna external_id
    end
    S->>S: dedup su external_id, applica esclusioni del sito
    S->>CAT: update_catalog(U, prodotti correnti)
    CAT->>CAT: delta, storico, delisting (mestiere del core)
```

## La pagina utente del plugin

Come l'utente sceglie *cosa osservare* è una scelta libera del plugin (navigazione per categorie, inserimento URL, ricerca…), con tre vincoli:

1. usa il **design system** del core;
2. offre il **dry-run** di anteprima (senza persistenza);
3. la selezione confermata crea le entry negli input del plugin.

È **distinta** dal Product Picker del core (che lavora sul catalogo già estratto). La pagina **admin** del plugin è a sua volta distinta: parametri operativi + test, mai selezione di contenuti.
