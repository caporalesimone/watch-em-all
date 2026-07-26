# Fase 9 — Dragon Store completo

> Stato: ☐ da iniziare · Prerequisiti: Fase 4 (e Fase 7 per il valore pieno) · [Indice del flusso](README.md)

> **✅ Punto chiarito (annotato 2026-07-23, deciso e implementato in `0.8.1`).** L'aggiunta di un URL **triggera lo scrape e scrive subito il prodotto nel catalogo**. Prima lo scrape all'aggiunta riempiva solo lo snapshot di visualizzazione, quindi per vedere un prezzo serviva attendere la run schedulata o premere *Scrape ora*: due tornate di richieste al sito per una sola intenzione dell'utente. La scrittura passa da `context.upsert_catalog` (mai da `update_catalog`): una consegna di un solo prodotto non dice nulla sugli altri e non deve attivare il delisting. **Vale la regola della cache** (nessun refetch entro il TTL del plugin). Il dry-run resta a scrittura zero.

> **🆕 Da fare in questa fase (annotato 2026-07-26).** Introdurre un livello utente **super-user** e legarci l'accesso allo *scrape manuale*: solo il super-user vede e usa il bottone *Scrape ora*, un utente normale non lo vede affatto. Per l'utente normale il flusso diventa "aggiungo un URL → è già risolto e nel mio catalogo", che con la scrittura immediata qui sopra è già completo. Direzione dichiarata: **lo scrape manuale va verso la rimozione** — è la via più rapida per far uscire richieste non pianificate verso un sito che ci chiede un `Crawl-delay`, e il cooldown SCR-R15 lo limita ma non lo elimina. Questa fase è il punto in cui restringerlo a un ruolo, non ancora in cui toglierlo.

## Obiettivo

Portare il primo scraper dal "prodotto singolo" alla configurazione ricca: categorie con paginazione, dedup, esclusioni del sito, UI utente completa con dry-run, e la gestione del ciclo di vita del catalogo (delisting e pulizie).

## Risultato apprezzabile

Incolli l'URL di una categoria, vedi l'anteprima in dry-run, confermi: decine di prodotti entrano nel catalogo a ogni run. I prodotti spariti dal sito si grigiano da soli; li pulisci con un click.

## MVP

### Backend

- [ ] **9.B1 — Riconoscimento URL categoria + fixture** (~1h): pattern `.sp.uw` dalla [pre-analisi](../../docs/implemented-plugins/dragon-store/capabilities.md#pre-analisi-del-sito-giugno-2026-una-pagina-di-categoria), fixture di categoria salvate, watch `kind=category`. *Verifica: URL categoria e URL prodotto distinti correttamente.*
- [ ] **9.B2 — Parsing delle card di categoria** (~1h): estrazione dalle card `resultBox.prod` (titolo, prezzi, id, disponibilità). *Verifica: test verdi sulle fixture di categoria.*
- [ ] **9.B3 — Paginazione delle categorie** (~1h): attraversamento delle pagine su categorie grandi, una richiesta alla volta (chiude DRG-Q4). *Verifica: categoria reale multi-pagina → tutti i prodotti.*
- [ ] **9.B4 — Dedup con priorità** (~1h): priorità categoria su prodotto singolo (DRG-R3). *Verifica: input sovrapposti → zero duplicati.*
- [ ] **9.B5 — Filtro ammaccati per-categoria** (~1h): flag `include_ammaccati` per watch di categoria (default false, filtro via prefisso del titolo, esclusi conteggiati in `products_excluded`); prodotti singoli mai filtrati e "l'inclusione vince" (DRG-R4/R7/R8). *Verifica: stesso ammaccato escluso da una categoria e incluso da un'altra → consegnato.*
- [ ] **9.B6 — Delisting end-to-end** (~1h): `removed` nel delta attivato end-to-end, riattivazione se il prodotto ricompare. *Verifica: prodotto tolto dalla fixture → `removed`; ricompare → riattivato.*
- [ ] **9.B7 — Pulizie catalogo** (~1h): endpoint rimuovi-delistati / selettiva / svuota, con cascate dichiarate. *Verifica: cascate corrette su carrelli e storico.*
- [ ] **9.B8 — Ruolo super-user + scrape manuale ristretto** (~1h): nuovo livello utente `super-user` tra `user` e `admin`; le rotte `POST`/`GET .../scrape-now` richiedono quel livello e rispondono `403` a un utente normale. *Verifica: utente normale → 403 su entrambe; super-user → invariato; admin → invariato.*
- [ ] **9.B9 — Notifica di delisting nel carrello** (~1h): **mancava** — oggi il delisting di un prodotto non genera alcun evento. Nuovo tag `PRODUCT_DELISTED` tra quelli disponibili e attivabili per carrello: se un prodotto del carrello viene delistato e la notifica è attiva, l'utente viene informato. Va **rivista ALERT-R12**, che oggi dice "i prodotti delistati non producono mai un tag" — è esattamente la regola che ha fatto passare inosservato il caso. La forma corretta: il delisting è un evento che si emette **una volta sola** alla transizione (serve `removed` nella baseline di `alert_snapshot`, che oggi esclude i membri delistati), mentre un prodotto già delistato continua a non produrre eventi di prezzo o disponibilità. Da chiarire in fase: se emettere anche l'evento inverso quando un prodotto ricompare (`_update_mutable_fields` lo riporta già a `removed=False`). *Verifica: prodotto delistato → un solo evento nel digest, non uno per run; tag disattivato → nessun evento; prodotto già delistato → nessun evento di prezzo.*

### Frontend

- [ ] **9.F1 — Lista watches completa** (~1h): input attivi con tipo, conteggi e stato del toggle ammaccati; rimozione ([features](../../docs/implemented-plugins/dragon-store/features.md)). *Verifica: lista fedele allo stato del plugin.*
- [ ] **9.F2 — Aggiunta con riconoscimento + toggle ammaccati** (~1h): riconoscimento automatico del tipo di URL, toggle **"Includi ammaccati"** per le categorie (default off, modificabile dopo), **avviso in rosso** sull'anteprima di un prodotto singolo AMMACCATO. *Verifica: toggle riflesso nell'anteprima.*
- [ ] **9.F3 — Dry-run delle categorie** (~1h): anteprima con la tabella risultati condivisa, conteggi inclusi/esclusi. *Verifica: flusso anteprima → conferma → entry.*
- [ ] **9.F5 — Bottone *Scrape ora* legato al livello utente** (~30m): il bottone e il countdown compaiono solo per super-user e admin; per un utente normale non esiste nel DOM, non è solo disabilitato. *Verifica: stessa pagina con i due ruoli → il bottone c'è / non c'è.*
- [ ] **9.F6 — Toggle della notifica di delisting** (~30m): `PRODUCT_DELISTED` nella lista dei tag attivabili per carrello, con la stessa forma degli altri, e reso nel digest e nella cronologia in-app. *Verifica: toggle riflesso nel digest del run successivo.*
- [ ] **9.F4 — Pulizie catalogo nel Picker** (~1h): righe delistate grigiate, azioni "rimuovi delistati" / modalità delete / svuota con conferme che dichiarano le cascate ([catalog feature](../../docs/3-features/user/catalog-and-product-picker.md)). *Verifica: conferme esplicite, tabella coerente dopo ogni azione.*

## Definition of Done

- [ ] Monitoraggio per categoria operativo nelle run schedulate, con contatori coerenti nel monitoring.
- [ ] I punti aperti DRG-Q1..Q7 risolti o aggiornati nella doc del plugin.
- [ ] Idempotenza confermata anche con categorie (seconda run senza cambi → zero delta).
- [ ] [docs](../../docs/) aggiornata in inglese con la sola parte implementata in questa fase (DOC-12).

## Riferimenti

[Dragon Store](../../docs/implemented-plugins/dragon-store/overview.md) · [scraper-plugin (contratto)](../../docs/3-features/plugins/scraper-plugin.md)
