# Fase 14 — Sito usabile da mobile

> Stato: 💡 idea / da dettagliare · **post-1.0** (oltre il perimetro della [1.0](../1-business/product-overview.md)) · Prerequisiti: Fase 12 (1.0) · [Indice del flusso](README.md)
>
> **Annotata il 2026-07-27.** Il sito oggi **non è usabile da telefono**: si vede male. È stato costruito assumendo uno schermo desktop, e la cosa non è mai stata affrontata. Gli MVP qui sotto sono abbozzati e vanno dettagliati (analisi → proposta → ok) prima di diventare lavoro reale.

## Obiettivo

Rendere il sito effettivamente usabile su uno schermo di telefono. Non "un'app mobile", non un secondo frontend: le stesse pagine che si adattano, con la navigazione raggiungibile e i contenuti densi (tabelle, grafici) resi in una forma che su 375 px di larghezza abbia senso.

Il lavoro è diviso in due blocchi con priorità e complessità molto diverse: **14.1** le pagine utente, **14.2** l'area di amministrazione — che va discussa prima, perché è la parte cara.

## Risultato apprezzabile

Apri Watch 'Em All dal telefono mentre sei in negozio, controlli il prezzo di un prodotto e lo stato di un carrello, senza zoomare e senza scorrimento orizzontale.

## 14.1 — Pagine utente

Perimetro: `/` (dashboard), `/catalog`, `/carts` e `/carts/[id]`, `/price-history`, `/alerts` e `/alerts/[id]`, `/profile`, più login e cambio password.

- [ ] **14.1.B1 — Ricognizione e breakpoint** (~1h): stabilire i target (telefono ~375 px, tablet ~768 px), verificare cosa si rompe davvero pagina per pagina e con quale sintomo (overflow orizzontale, testo illeggibile, controlli irraggiungibili), e fissare i breakpoint Tailwind da usare in modo uniforme. *Verifica: elenco dei problemi reali, non presunti, con priorità.*
- [ ] **14.1.F1 — Navigazione** (~1h): la sidebar oggi è una colonna fissa. Su mobile serve una forma raggiungibile con il pollice — drawer o barra inferiore, da decidere in 14.1.B1. *Verifica: ogni sezione raggiungibile da telefono senza zoom.*
- [ ] **14.1.F2 — Tabelle dense** (~1h): catalogo e carrelli sono tabelle a molte colonne. Su schermo stretto vanno rese come schede impilate, o con le colonne secondarie collassate. *Verifica: nessuno scorrimento orizzontale della pagina.*
- [ ] **14.1.F3 — Grafici dei prezzi** (~1h): i chart di fase 8 devono restare leggibili — assi, tooltip e selettori di intervallo sono pensati per il mouse. Da valutare il tocco al posto dell'hover. *Verifica: tooltip utilizzabile con il dito.*
- [ ] **14.1.F4 — Form e dialoghi** (~1h): aggiunta URL, impostazioni del carrello, canali di notifica, cambio password. *Verifica: nessun campo tagliato, tastiera che non copre il pulsante di conferma.*

## 14.2 — Area amministrazione ⛔ da discutere

> **Non implementare nulla di questo blocco prima di averlo discusso e deciso con Simone**, come da sua indicazione: la complessità va valutata prima di impegnarsi.

Il punto da decidere è **se valga la pena**. L'area admin ha un solo utilizzatore, che ci lavora da un PC; le sue pagine sono le più ostili al mobile di tutto il progetto, e adattarle costa più delle pagine utente messe insieme:

- **i log** (`/admin/logs`) sono una tabella densa a quattro colonne con filtri, ricerca, chip delle sorgenti, paginazione e un tail dal vivo — su 375 px non c'è una risposta ovvia;
- **il monitoraggio degli scraper** vive di tabelle e serie temporali affiancate;
- **il calendario degli slot** (fase 10) è per costruzione una griglia larga.

Alternative da mettere sul tavolo quando se ne parla, in ordine crescente di costo: lasciare l'area admin esplicitamente desktop-only, con un avviso onesto quando la si apre da telefono; renderne utilizzabili **solo alcune** pagine (i log in lettura sono il candidato più probabile: è la cosa che vorresti guardare al volo); oppure adattare tutto.

## Definition of Done

- [ ] Nessuna pagina in perimetro produce scorrimento orizzontale a 375 px.
- [ ] Ogni azione raggiungibile senza zoom.
- [ ] Perimetro di 14.2 deciso esplicitamente — anche se la decisione è "non si fa".
- [ ] [docs](../../docs/) aggiornata in inglese con la sola parte implementata (DOC-12).

## Riferimenti

[Product overview](../1-business/product-overview.md) · [Fase 12 — Rifinitura e 1.0](phase-12-polish-v1.md)
