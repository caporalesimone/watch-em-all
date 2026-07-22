# Glossario — termini ancora da realizzare

> **Layer 1 — Business** · Audience: tutti.
>
> I termini **già in uso** nel prodotto realizzato (Scraper, Notifier, Plugin, Catalogo, Product Picker, Carrello, Modalità carrello, Adjustment, Soglia, Provenienza, Identità del prodotto, Non disponibile, Delistato, Run, Slot, Cache di scrape, Dry-run/Test, Core, Worker) sono stati migrati nel glossario inglese canonico: [`docs/1-business/glossary.md`](../../docs/1-business/glossary.md). Qui restano **solo i termini che nominano capacità non ancora costruite** (fase 6+).

| Termine | Definizione |
|---|---|
| **Alert digest** | La notifica aggregata: il **diff** di tutti i carrelli rispetto all'ultima notifica, in un unico messaggio. |
| **Summary** | Il report periodico opzionale: una **fotografia** dello stato corrente dei carrelli (non un diff). |
| **Cadenza (summary)** | Quando l'utente riceve il **report periodico** (settimanale/mensile, opt-in). Gli **alert** invece non hanno cadenza: sono **event-driven**, scattano a fine scrape. *Quali* avvisi ricevere si decide carrello per carrello. |
| **Baseline** | Lo stato di riferimento con cui il sistema confronta per capire "cosa è cambiato" dall'ultima notifica. |
| **Cancellazione differita** | La cancellazione di un account da parte dell'admin: l'account viene disabilitato e marcato **in cancellazione** con una **scadenza** (default 30 giorni); fino ad allora è annullabile con un tasto (torna disabilitato), dopo viene eliminato automaticamente con tutti i suoi dati. |
| **Storico alert** | L'archivio interno delle notifiche dell'utente, consultabile dall'app anche senza canali configurati, con stato di lettura. |
| **Storico prezzi** | L'archivio permanente delle variazioni di prezzo e disponibilità, base dei grafici. |
| **Minimo storico (all-time low)** | Il prezzo più basso mai registrato per un prodotto nello storico dell'utente. Mostrato come badge e disponibile come tipo di avviso ("ribasso al minimo storico"). |
| **Indicatore di convenienza** | Etichetta sintetica (*Ottimo momento / Nella media / Conviene aspettare*) calcolata con statistiche trasparenti sullo storico; sempre accompagnata dai numeri che la generano, mai una previsione certa. |
| **Export dati** | Download self-service di tutti i propri dati (catalogo, storici, carrelli, notifiche) in JSON o CSV, dal Profilo. |
