# Fase 3 — Catalogo e primo scrape

> Stato: 🚧 in corso — **primo MVP fatto: Gestione utenti (`0.3.0`)**; il catalogo/scrape segue · Prerequisiti: Fase 2 · [Indice del flusso](README.md)

## Obiettivo

I dati veri entrano nel sistema: contratto `Product`, catalogo con delta e storico, Dragon Store nella versione minima (URL di prodotti singoli), Product Picker per vederli. Niente scheduling: lo scrape si lancia a mano.

## Risultato apprezzabile

Incolli l'URL di un prodotto Dragon Store nella pagina del plugin → "Scrape ora" → il prodotto è nel tuo Product Picker con foto, prezzi, sconto e provenienza. Rilanci: zero duplicati, e se il prezzo è cambiato lo storico lo registra.

## MVP

- [x] **3.U — Gestione utenti (MVP iniziale)** (`0.3.0`): anticipato dalla [Fase 10](#) perché serve un account `user` per provare il resto della fase (i ruoli **non si sovrappongono**: l'admin governa, non possiede carrelli — [personas-and-roles](../1-business/personas-and-roles.md)). Backend: `POST`/`GET /api/admin/users` (admin-only; crea con cambio-pwd forzato, elenca). Frontend: shell **sdoppiato per ruolo** + pagina admin **Users** (crea + elenca; password temporanea generabile in chiaro, 8 alfanumerici). Rimandato alla Fase 10: reset password, disabilita/riabilita, cancellazione differita + restore, filtri, ordinamento ultimo accesso, notifiche di cortesia. Dettaglio: [user-management](../3-features/admin/user-management.md). *Verifica: l'admin crea un `user`, ci si logga; endpoint admin-only.*

### Backend

- [x] **3.B1 — Tabelle catalogo + modello Product** (~1h): modello [Product](../4-capabilities/contracts/product.md), tabelle `products`/`price_history` con UNIQUE identità ([schema](../4-capabilities/database/schema.md)). *Verifica: vincoli di unicità rispettati (insert duplicato → conflitto gestito).*
- [x] **3.B2 — Delta del Catalog Update Service** (~1h): classificazione nuovo/aggiornato/prezzo/disponibilità ([catalog-update-service](../4-capabilities/core/catalog-update-service.md)). *Verifica: unit test tabellari su casi nuovi/variati/invariati.*
- [x] **3.B3 — Risoluzione prezzi + scrittura storico** (~1h): regole di risoluzione prezzo, entry di `price_history` solo sui cambi. *Verifica: unit test; secondo passaggio identico → zero entry.*
- [x] **3.B4 — Client HTTP del contesto v0** (~1h): `context.http` con politeness e timeout ([plugin-context](../4-capabilities/core/plugin-context.md)). **Mock**: niente retry (lo aggiunge 3.B5). *Verifica: due richieste consecutive rispettano il ritardo.*
- [x] **3.B5 — Client HTTP: retry + contatore** (~1h): retry con backoff e contatore `http_requests` instrumentato. *Verifica: errore transitorio → ritenta; contatore coerente.*
- [x] **3.B6 — Dragon Store: parsing scheda prodotto** (~1h): fixture salvate; **JSON-LD `Product` come fonte primaria** + DOM per il listino (`tr.D1`), decode `cp1252` + `html.unescape`, tutto **scoped alla tabella principale** (la pagina ha 20-46 prodotti correlati) — vedi [studio ad hoc](../implemented-plugins/dragon-store/capabilities.md#scheda-prodotto-gp-parsing-reale-studio-ad-hoc-giugno-2026); titolo, prezzi, immagine, marca. *Verifica: test verdi sulle fixture.*
- [x] **3.B7 — Dragon Store: identità + disponibilità** (~1h): `external_id` = id numerico nativo (via `identity_seed`); `is_available` da `offers.availability` a **3 stati** — `InStock`→true, `OutOfStock`→false, `PreOrder`→true (+ tag `"Pre Order"`), sconosciuto→false+log. *Verifica: stessa pagina due volte → stesso external_id; i 3 stati mappati sulle fixture.*
- [x] **3.B8 — Watches v0 + run_for_user** (~1h): tabella watches del plugin (solo `kind=product`), `run_for_user` che consegna i Product al core. *Verifica: watch + run → prodotto nel catalogo.*
- [x] **3.B9 — run_test + route del plugin** (~1h): `run_test` senza scritture, route `test` e `watches`. *Verifica: dry-run da Swagger non scrive nulla.*
- [x] **3.B10 — API catalogo** (~1h): `GET /api/catalog` paginato/ordinabile/filtrabile. *Verifica: da Swagger su catalogo popolato.*
- [x] **3.B11 — Scrape-now (rotta del plugin)** (~1h): `POST /api/plugins/dragon-store/scrape-now` — scrape immediato del **solo utente richiedente** (scrive via Catalog Update Service), background semplice nel web; `GET` gemello per lo stato del cooldown. **Cooldown per-scraper**: entro l'intervallo → **429** col tempo rimanente (SCR-R15). La meccanica (cooldown via tabella core **`scrape_cooldown`** — anchor "ultimo scrape" per *(scraper, utente)*, scritto **all'avvio** + dispatch a `run_for_user`) è **fornita dall'infrastruttura del core** (il web auto-monta la rotta per gli scraper che implementano `run_for_user`). **Mock dichiarato (regola #7)**: l'intervallo è una **costante (default 1h)**, sostituita dal parametro admin riservato in [4.B10/4.F2](phase-04-worker-scheduling.md). *Verifica: due scrape-now ravvicinati → il secondo è rifiutato (429) col tempo rimanente; trascorso l'intervallo → si popola.*
- [x] **3.B12 — `tags`, `brand`, `category` + title sanitizer** (~2h): estende il contratto `Product` con **`brand`** (`BrandRef{text, link?}`, [PROD-R6](../4-capabilities/contracts/product.md)), **`tags`** (tag, PROD-R5) e **`category`** (breadcrumb `CategoryRef{text, link?}`, PROD-R7), persistiti dal Catalog Update Service (CATSVC-R5); la base `ScraperPlugin` fornisce `add_tag()`/`get_tags()` ([SCR-R16](../3-features/plugins/scraper-plugin.md)) e `add_child()`/`get_path()` (SCR-R17), per-prodotto; **sanitizer specifico di Dragon Store** (JSON di etichette hardcoded) toglie le etichette dal titolo → tag, + tag `"Pre Order"` da `PreOrder`; **categoria** dal JSON-LD `BreadcrumbList`. *Verifica: titolo "OFFERTA RAVEN PRIME - X" → name "X" + tags ["Offerta Raven Prime"]; preorder → "Pre Order"; brand con link; category breadcrumb non vuoto.*
- [x] **3.B13 — Watch con titolo/snapshot + dedup URL** (~1h): `POST /watches` rifiuta un URL già presente (409) e risolve il titolo con uno scrape one-off, salvando uno **snapshot** del prodotto sulla watch (`snapshot_json`), aggiornato a ogni run; la pagina utente mostra le watch come la preview. *Verifica: add → titolo subito; add doppione → 409.*

### Frontend

- [x] **3.F1 — Tabella del Product Picker** (~1h): foto (hover-zoom con piccolo ritardo), titolo+marca+tag+categoria, prezzi (sconto come badge sotto il prezzo, non colonna separata), provenienza (link allo scraper); foto/titolo come link al prodotto (niente colonna "Apri") ([catalog-and-product-picker](../3-features/user/catalog-and-product-picker.md)). *Verifica: tabella popolata e leggibile; categoria e tag visibili.*
- [x] **3.F2 — Picker: paginazione, ordinamento, ricerca** (~1h). *Verifica: navigazione fluida su catalogo reale.*
- [x] **3.F3 — Pagina plugin: gestione watch** (~1h): inserimento URL prodotto, lista watch con rimozione. *Verifica: aggiunta e rimozione da browser.*
- [x] **3.F4 — Dry-run UI + scrape-now** (~1h): dry-run con tabella risultati condivisa; bottone **"Scrape ora" sulla pagina dello scraper** con **trattamento sobrio**: etichetta invariata + **didascalia col tempo rimanente** quando il cooldown non è trascorso (stato letto dal `GET` di 3.B11), e **popup di conferma** alla pressione che ricorda ogni quanto è disponibile (intervallo in forma leggibile: *15 minuti* / *1 ora* / *12 ore e 15 minuti*). Trattamento più ricco (countdown nell'etichetta + progress bar) rimandato ai [future improvements](../../docs/future-improvements/README.md). *Verifica: URL → anteprima → conferma → scrape → tabella popolata; secondo scrape-now immediato → bottone disabilitato col timer e 429 lato server.*

## Definition of Done

- [ ] Flusso end-to-end da browser: aggiungi URL → scrape-now → prodotto in tabella.
- [ ] Idempotenza: secondo scrape senza cambi sul sito → zero nuovi prodotti, zero entry di storico.
- [ ] Il core non contiene una riga specifica di Dragon Store.
- [ ] [docs](../../docs/) aggiornata in inglese con la sola parte implementata in questa fase (DOC-12).

## Riferimenti

[scraper-plugin (contratto)](../3-features/plugins/scraper-plugin.md) · [scraper-development-guide](../plugin-development/scraper-development-guide.md) · [Dragon Store](../implemented-plugins/dragon-store/overview.md)
