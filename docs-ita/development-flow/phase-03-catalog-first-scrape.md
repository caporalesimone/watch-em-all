# Fase 3 — Catalogo e primo scrape

> Stato: ☐ da iniziare · Prerequisiti: Fase 2 · [Indice del flusso](README.md)

## Obiettivo

I dati veri entrano nel sistema: contratto `Product`, catalogo con delta e storico, Dragon Store nella versione minima (URL di prodotti singoli), Product Picker per vederli. Niente scheduling: lo scrape si lancia a mano.

## Risultato apprezzabile

Incolli l'URL di un prodotto Dragon Store nella pagina del plugin → "Scrape ora" → il prodotto è nel tuo Product Picker con foto, prezzi, sconto e provenienza. Rilanci: zero duplicati, e se il prezzo è cambiato lo storico lo registra.

## MVP

### Backend

- [ ] **3.B1 — Tabelle catalogo + modello Product** (~1h): modello [Product](../4-capabilities/contracts/product.md), tabelle `products`/`price_history` con UNIQUE identità ([schema](../4-capabilities/database/schema.md)). *Verifica: vincoli di unicità rispettati (insert duplicato → conflitto gestito).*
- [ ] **3.B2 — Delta del Catalog Update Service** (~1h): classificazione nuovo/aggiornato/prezzo/disponibilità ([catalog-update-service](../4-capabilities/core/catalog-update-service.md)). *Verifica: unit test tabellari su casi nuovi/variati/invariati.*
- [ ] **3.B3 — Risoluzione prezzi + scrittura storico** (~1h): regole di risoluzione prezzo, entry di `price_history` solo sui cambi. *Verifica: unit test; secondo passaggio identico → zero entry.*
- [ ] **3.B4 — Client HTTP del contesto v0** (~1h): `context.http` con politeness e timeout ([plugin-context](../4-capabilities/core/plugin-context.md)). **Mock**: niente retry (lo aggiunge 3.B5). *Verifica: due richieste consecutive rispettano il ritardo.*
- [ ] **3.B5 — Client HTTP: retry + contatore** (~1h): retry con backoff e contatore `http_requests` instrumentato. *Verifica: errore transitorio → ritenta; contatore coerente.*
- [ ] **3.B6 — Dragon Store: parsing scheda prodotto** (~1h): fixture salvate, selettori e id nativo dalla [pre-analisi](../implemented-plugins/dragon-store/capabilities.md#pre-analisi-del-sito-giugno-2026-una-pagina-di-categoria), titolo e prezzi. *Verifica: test verdi sulle fixture.*
- [ ] **3.B7 — Dragon Store: identità + disponibilità** (~1h): `external_id` = id numerico nativo (via `identity_seed`), `is_available` da `fullAV`/`noAV`. *Verifica: stessa pagina due volte → stesso external_id.*
- [ ] **3.B8 — Watches v0 + run_for_user** (~1h): tabella watches del plugin (solo `kind=product`), `run_for_user` che consegna i Product al core. *Verifica: watch + run → prodotto nel catalogo.*
- [ ] **3.B9 — run_test + route del plugin** (~1h): `run_test` senza scritture, route `test` e `watches`. *Verifica: dry-run da Swagger non scrive nulla.*
- [ ] **3.B10 — API catalogo** (~1h): `GET /api/catalog` paginato/ordinabile/filtrabile. *Verifica: da Swagger su catalogo popolato.*
- [ ] **3.B11 — Scrape-now** (~1h): `POST /api/catalog/scrape-now` con guardia "solo catalogo vuoto" (409 altrimenti), esecuzione in background semplice nel web. *Verifica: catalogo vuoto → si popola; non vuoto → 409.*

### Frontend

- [ ] **3.F1 — Tabella del Product Picker** (~1h): foto, titolo, prezzi, sconto, provenienza, link ([catalog-and-product-picker](../3-features/user/catalog-and-product-picker.md)). *Verifica: tabella popolata e leggibile.*
- [ ] **3.F2 — Picker: paginazione, ordinamento, ricerca** (~1h). *Verifica: navigazione fluida su catalogo reale.*
- [ ] **3.F3 — Pagina plugin: gestione watch** (~1h): inserimento URL prodotto, lista watch con rimozione. *Verifica: aggiunta e rimozione da browser.*
- [ ] **3.F4 — Dry-run UI + scrape-now** (~1h): dry-run con tabella risultati condivisa, bottone "Scrape ora" visibile solo a catalogo vuoto. *Verifica: flusso URL → anteprima → conferma → scrape → tabella popolata.*

## Definition of Done

- [ ] Flusso end-to-end da browser: aggiungi URL → scrape-now → prodotto in tabella.
- [ ] Idempotenza: secondo scrape senza cambi sul sito → zero nuovi prodotti, zero entry di storico.
- [ ] Il core non contiene una riga specifica di Dragon Store.
- [ ] [docs](../../docs/) aggiornata in inglese con la sola parte implementata in questa fase (DOC-12).

## Riferimenti

[scraper-plugin (contratto)](../3-features/plugins/scraper-plugin.md) · [scraper-development-guide](../plugin-development/scraper-development-guide.md) · [Dragon Store](../implemented-plugins/dragon-store/overview.md)
