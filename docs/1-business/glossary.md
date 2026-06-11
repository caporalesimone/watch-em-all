# Glossario

> **Layer 1 — Business** · Audience: tutti.

| Termine | Definizione |
|---|---|
| **Scraper** | Plugin che osserva un singolo sito e-commerce ed estrae prodotti (prezzi, disponibilità). Internamente lavora **in modo sequenziale** (un solo flusso di lavoro per scraper); è il sistema a poterne eseguire più d'uno in parallelo. |
| **Notifier** | Plugin che consegna le notifiche su un canale (email, Discord, …). |
| **Plugin** | Unità autonoma full-stack (backend + interfaccia) che estende il sistema. Due famiglie: scraper e notifier. Ogni plugin è configurabile a livello **admin** (parametri di sistema) e a livello **utente** (parametri personali). |
| **Catalogo** | L'insieme dei prodotti estratti per un utente. Personale e isolato per utente. |
| **Product Picker** | La tabella del catalogo da cui l'utente sceglie i prodotti da mettere nei carrelli. Distinta dalle pagine dei singoli scraper (dove si sceglie *cosa osservare sul sito*). |
| **Carrello (cart)** | Gruppo di prodotti del catalogo con soglia di risparmio e tipi di avviso. Unità minima di monitoraggio con notifica. |
| **Modalità carrello** | `scraper_specific`: prodotti di un solo sito, totali calcolati con le regole di quel sito (adjustments). `cross`: prodotti da siti diversi, anche lo stesso prodotto ripetuto una volta per sito; nessun adjustment; **provenienza sempre visibile** per riga. Immutabile dopo la creazione. |
| **Adjustment** | Voce correttiva sul totale di un carrello scraper-specific, calcolata dal plugin: sconto a soglia (positiva) o costo aggiuntivo come la spedizione (negativa). |
| **Soglia** | Valore (assoluto in € o percentuale di sconto) al di sotto/sopra del quale scatta l'avviso di carrello. |
| **Provenienza** | Il sito/scraper da cui proviene un prodotto. Mostrata sempre (icona + nome) nel Product Picker, nelle card dei carrelli e nelle notifiche — indispensabile nei carrelli cross. |
| **Identità del prodotto** | Il modo in cui il sistema riconosce "lo stesso prodotto" tra un'osservazione e l'altra: un identificatore stabile fornito dallo scraper (`external_id`), insieme al plugin e all'utente. |
| **Non disponibile (`is_available = false`)** | Prodotto temporaneamente esaurito sul sito. Resta nel catalogo e nei carrelli, escluso dai totali finché non torna. Deciso dallo **scraper**. |
| **Delistato (`removed`)** | Prodotto sparito dal sito (non più trovato dallo scraper). Resta nel catalogo, grigiato e ignorato, finché l'utente non lo pulisce manualmente. Deciso dal **core**. |
| **Alert digest** | La notifica aggregata: il **diff** di tutti i carrelli rispetto all'ultima notifica, in un unico messaggio. |
| **Summary** | Il report periodico opzionale: una **fotografia** dello stato corrente dei carrelli (non un diff). |
| **Cadenza** | Quando l'utente riceve gli alert: giorni della settimana + orario, a livello di account. *Quali* avvisi ricevere si decide invece carrello per carrello. |
| **Baseline** | Lo stato di riferimento con cui il sistema confronta per capire "cosa è cambiato" dall'ultima notifica. |
| **Run (di scrape)** | Una singola esecuzione di uno scraper, che processa tutti gli utenti che lo hanno configurato. Programmata dall'admin, da 1 a N volte al giorno. |
| **Slot** | Uno degli orari programmati di una run. Se il sistema era fermo, recupera lo slot più recente perso (uno solo). |
| **Dry-run / Test** | Esecuzione di prova di uno scraper che mostra i prodotti trovati **senza salvare nulla**. |
| **Core** | Il cuore del sistema: orchestra i plugin, possiede i dati, calcola carrelli e notifiche. Non conosce la logica interna dei plugin (né, ad esempio, il concetto di "categoria", che è interno agli scraper). |
| **Worker** | Il processo che fa girare le cose al momento giusto: esecuzioni scraper, notifiche, report. |
| **Storico alert** | L'archivio interno delle notifiche dell'utente, consultabile dall'app anche senza canali configurati, con stato di lettura. |
| **Storico prezzi** | L'archivio permanente delle variazioni di prezzo e disponibilità, base dei grafici. |
| **Minimo storico (all-time low)** | Il prezzo più basso mai registrato per un prodotto nello storico dell'utente. Mostrato come badge e disponibile come tipo di avviso ("ribasso al minimo storico"). |
| **Indicatore di convenienza** | Etichetta sintetica (*Ottimo momento / Nella media / Conviene aspettare*) calcolata con statistiche trasparenti sullo storico; sempre accompagnata dai numeri che la generano, mai una previsione certa. |
| **Export dati** | Download self-service di tutti i propri dati (catalogo, storici, carrelli, notifiche) in JSON o CSV, dal Profilo. |
