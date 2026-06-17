# Catalogo e Product Picker

> **Layer 3 — Feature utente** · Audience: architetti, developer · Testo + Mermaid, niente codice. Capability: [catalog-update-service](../../4-capabilities/core/catalog-update-service.md).

## Scopo

Il catalogo è l'insieme dei prodotti estratti dagli scraper per l'utente. Il **Product Picker** è la tabella con cui l'utente lo consulta, lo pulisce e seleziona i prodotti da mettere nei carrelli. Non esegue scraping: è pura selezione su dati già nel DB (le anteprime live sono delle pagine dei singoli plugin).

## Requisiti

- **CAT-R1** — Il catalogo è per-utente: contiene la somma dei prodotti estratti dagli scraper che l'utente ha configurato.
- **CAT-R2** — Ogni prodotto mostra sempre la **provenienza** (icona + nome dello scraper). Fondamentale per i carrelli cross ([use case 2](../../1-business/use-cases.md)).
- **CAT-R3** — I prodotti **non disponibili** restano nel catalogo (indicatore visivo), non vengono mai esclusi automaticamente.
- **CAT-R4** — I prodotti **delistati** (`removed`, assenti dall'ultimo scrape) restano in tabella grigiati, esclusi da carrelli e alert, finché l'utente non li pulisce. Se ricompaiono in uno scrape, tornano attivi.
- **CAT-R5** — La tabella è **paginata lato server**, ordinabile (titolo, prezzi, % sconto, scraper), filtrabile per scraper e ricercabile per titolo.
- **CAT-R6** — Azioni di pulizia: rimuovi delistati, rimozione selettiva (modalità delete), svuota catalogo. Tutte con conferma; la conferma **dichiara le conseguenze** (rimozione dai carrelli e perdita dello storico dei prodotti coinvolti).
- **CAT-R7** — **Scrape ora**: disponibile **solo a catalogo vuoto**, esegue gli scraper configurati dall'utente per popolarlo subito. Il server riverifica la condizione (catalogo non vuoto → richiesta rifiutata con errore esplicito). L'esecuzione è in background: la UI mostra l'avanzamento.
- **CAT-R8** — L'eliminazione di un prodotto dal catalogo lo rimuove **a cascata** dai carrelli e ne elimina lo storico prezzi.

## La tabella

| Colonna | Contenuto |
|---|---|
| Provenienza | Icona dello scraper (dal manifest), nome in hover |
| Foto | Immagine remota, dimensione fissa |
| Titolo | Nome prodotto |
| Prezzo pieno | Listino (o ultimo noto) |
| Prezzo scontato | Prezzo corrente |
| % sconto | Badge |
| Disponibilità | Indicatore (disponibile / esaurito / delistato) |
| Apri | Link alla pagina del prodotto sul sito (nuova tab) |

## Flussi

```mermaid
flowchart LR
    subgraph "Plugin scraper (pagina del sito)"
        CFG[L'utente sceglie<br/>cosa osservare]
    end
    subgraph "Scrape schedulato"
        RUN[Run dello scraper] --> CAT[(Catalogo<br/>per-utente)]
    end
    subgraph "Product Picker (core)"
        TAB[Tabella catalogo] --> SEL[Selezione righe]
        SEL --> CART[Aggiungi al carrello]
        TAB --> CLEAN[Pulizia: delistati /<br/>selezione / svuota]
    end
    CFG -.input dello scraper.-> RUN
    CAT --> TAB
```

Distinzione da tenere ferma (fonte frequente di confusione):

| | Pagina del plugin | Product Picker (core) |
|---|---|---|
| Scopo | Decidere **cosa osservare sul sito** | Scegliere prodotti **già nel catalogo** per i carrelli |
| Dati | Anteprima live dal sito (dry-run) | DB |
| Scrive | Input dello scraper (tabelle del plugin) | Membri dei carrelli |

## Ciclo "catalogo vuoto → primo popolamento"

```mermaid
sequenceDiagram
    participant U as Utente
    participant P as Pagina plugin
    participant PP as Product Picker
    participant W as Web (background)

    U->>P: configura cosa osservare
    U->>PP: catalogo vuoto → bottone "Scrape ora"
    U->>W: scrape-now
    W->>W: verifica catalogo vuoto + lock per-scraper
    W-->>U: avviato (job in background)
    W->>W: esegue gli scraper dell'utente
    U->>PP: il catalogo si popola
```

Negli altri casi il catalogo si aggiorna ai normali scrape schedulati: lo "Scrape ora" esiste solo per non far attendere ore il primo popolamento.
