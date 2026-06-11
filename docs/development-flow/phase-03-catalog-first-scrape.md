# Fase 3 — Catalogo e primo scrape

> Stato: ☐ da iniziare · Prerequisiti: Fase 2 · [Indice del flusso](README.md)

## Obiettivo

I dati veri entrano nel sistema: contratto `Product`, catalogo con delta e storico, Dragon Store nella versione minima (URL di prodotti singoli), Product Picker per vederli. Niente scheduling: lo scrape si lancia a mano.

## Risultato apprezzabile

Incolli l'URL di un prodotto Dragon Store nella pagina del plugin → "Scrape ora" → il prodotto è nel tuo Product Picker con foto, prezzi, sconto e provenienza. Rilanci: zero duplicati, e se il prezzo è cambiato lo storico lo registra.

## MVP

### Backend

- [ ] **3.B1 — Contratto Product + Catalog Update Service** (~4h): modello [Product](../4-capabilities/contracts/product.md), tabelle `products`/`price_history` con UNIQUE identità, delta (nuovo/aggiornato/prezzo/disponibilità), risoluzione prezzi ([catalog-update-service](../4-capabilities/core/catalog-update-service.md)). Unit test tabellari del delta. *Verifica: test verdi su casi nuovi/variati/invariati.*
- [ ] **3.B2 — Client HTTP del contesto** (~3h): `context.http` con politeness, timeout, retry, contatore richieste ([plugin-context](../4-capabilities/core/plugin-context.md)). *Verifica: due richieste consecutive rispettano il ritardo.*
- [ ] **3.B3 — Dragon Store v0: prodotto singolo** (~4h): parsing della scheda prodotto con fixture salvate (selettori e id nativo dalla [pre-analisi](../implemented-plugins/dragon-store/capabilities.md#pre-analisi-del-sito-giugno-2026-una-pagina-di-categoria)), `external_id` = id numerico nativo, `is_available` da `fullAV`/`noAV`. *Verifica: stessa pagina due volte → stesso external_id.*
- [ ] **3.B4 — Watches v0 + run_for_user + run_test** (~3h): tabella watches del plugin (solo `kind=product`), `run_for_user`, `run_test` senza scritture, route `test` e `watches`. *Verifica: dry-run da Swagger non scrive nulla.*
- [ ] **3.B5 — API catalogo + scrape-now** (~3h): `GET /api/catalog` paginato/ordinabile/filtrabile; `POST /api/catalog/scrape-now` con guardia "solo catalogo vuoto" (409 altrimenti) ed esecuzione in background semplice nel web. *Verifica: catalogo vuoto → si popola; non vuoto → 409.*

### Frontend

- [ ] **3.F1 — Product Picker v0** (~3h): tabella catalogo (foto, titolo, prezzi, sconto, provenienza, link) con paginazione, ordinamento e ricerca ([catalog-and-product-picker](../3-features/user/catalog-and-product-picker.md)). *Verifica: tabella popolata e navigabile.*
- [ ] **3.F2 — Pagina plugin v0 + scrape-now** (~3h): inserimento URL prodotto, lista watch con rimozione, dry-run con tabella risultati condivisa; bottone "Scrape ora" visibile solo a catalogo vuoto. *Verifica: flusso URL → anteprima → conferma → scrape → tabella popolata.*

## Definition of Done

- [ ] Flusso end-to-end da browser: aggiungi URL → scrape-now → prodotto in tabella.
- [ ] Idempotenza: secondo scrape senza cambi sul sito → zero nuovi prodotti, zero entry di storico.
- [ ] Il core non contiene una riga specifica di Dragon Store.

## Riferimenti

[scraper-plugin (contratto)](../3-features/plugins/scraper-plugin.md) · [scraper-development-guide](../plugin-development/scraper-development-guide.md) · [Dragon Store](../implemented-plugins/dragon-store/overview.md)
