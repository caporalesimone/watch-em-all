# Fase 5 — Carrelli

> Stato: 🚧 in corso (avviata 2026-06-29) · Prerequisiti: Fase 3 (la 4 può procedere in parallelo) · [Indice del flusso](README.md)

## Obiettivo

Il cuore funzionale: carrelli nelle due modalità, totali calcolati, adjustments, soglia. Da qui in poi i due [use case](../1-business/use-cases.md) si vedono a schermo.

## Risultato apprezzabile

Crei "Wishlist giochi" (scraper-specific): la card mostra totale pieno barrato, scontato, lo sconto a soglia di Dragon Store, la stima finale e la barra verso la tua soglia. Crei "Fotocamera" (cross) con lo stesso prodotto da più watch: ogni riga mostra il suo negozio.

## MVP

### Trasversali (da fare tra le prime cose)

- [x] **5.T1 — Tag `latest` sulle immagini al release** (~30m): in `publish.yml`, oltre a `:x.y.z`, pushare anche **`:latest`** per `watch-em-all` e `watch-em-all-ops` (due tag nello stesso build-push, o `docker/metadata-action`). **Decisione (2026-06-27, Simone)**: si vuole `latest` come comodità — **inverte la chiosa "mai `latest`"** sulle *nostre* immagini in [ci.md](../infrastructure/ci.md) e [deployment.md](../infrastructure/deployment.md): quando atterra, aggiornare quelle due note. Il **pinning di `WEA_VERSION` resta il default consigliato** in deployment (`latest` = prova rapida / "ultima"). **INF-1 non cambia**: riguarda il pinning delle immagini *upstream* (`postgres:16`, `pgweb`, base images), non la pubblicazione di un `latest` per i nostri artefatti. *Verifica: push di un tag `x.y.z` → su GHCR compaiono sia `x.y.z` sia `latest` per entrambe le immagini.*

### Backend

- [x] **5.B1 — Tabelle + CRUD carrelli** (~1h): `carts`/`cart_members` (UNIQUE, cascate), API CRUD ([endpoints](../api/endpoints.md#carrelli--cart-engine)). *Verifica: ciclo completo via Swagger.* — modelli core `Cart`/`CartMember`, router `/api/carts` (create con `mode` fisso + validazione scraper, list, get, rename, delete; per-utente DB-R1); membri 5.B2, stato calcolato 5.B3.
- [x] **5.B2 — Regole di modalità + membri** (~1h): modalità immutabile; scraper-specific accetta solo prodotti del suo scraper; API membri. *Verifica: vincoli rifiutati con errori chiari via Swagger.* — `POST`/`DELETE /api/carts/{id}/items`; add a batch atomico (solo catalogo dell'utente, niente delistati, valuta unica, scraper coerente), idempotente; remove no-op sui non-membri. La compatibilità multi-scraper nel Picker è rinviata a [6.F0](phase-06-alerts-in-app.md).
- [x] **5.B3 — Cart Engine: attivi/esclusi e totali** (~1h): stato calcolato, totale pieno/scontato, esclusione indisponibili ([cart-engine](../4-capabilities/core/cart-engine.md)). *Verifica: unit test tabellari sui casi normativi di [carts.md](../3-features/user/carts.md).* — `src/core/cart_engine.py` (`evaluate_cart` puro, DTO `CartState`; flag `has_delisted`), `Adjustment{id,description,amount,params}` in `contracts.py`, base `ScraperPlugin.get_adjustments` (default `[]`), API espone card (lista) e dettaglio con i membri; adjustments via callable iniettato dal router.
- [x] **5.B4 — Cart Engine: soglia** (~1h): soglia memorizzata come **valore assoluto in €** (`threshold_amount > 0`; la % è solo un aiuto di input nella UI, convertita a € prima dell'invio — decisione Simone 2026-06-29, **inverte CART-R9/R10**); confronto **stima finale ≤ soglia**, niente soglia senza attivi (CART-R12). *Verifica: unit test sul confronto e sulla guardia zero-attivi.*
- [x] **5.B5 — Adjustments Dragon Store** (~1h): `get_adjustments` con soglie configurabili, integrazione nel calcolo ([dragon-store features](../implemented-plugins/dragon-store/features.md)). *Verifica: carrello sopra soglia → voce di sconto nello stato calcolato.* — classe regole `backend/adjustments.py` (fasce non cumulabili 5/10/15% + spedizione €5/gratis≥100), override `get_adjustments`, chiavi i18n `dragon_store.adjustments.*` (prefisso dinamico esente nel gate). Valori cablati in fase 5; admin-editabili in fase 7+/9.

### Frontend

- [x] **5.F1 — Pagina carrelli: CRUD** (~1h): creazione (con scelta modalità), modifica, eliminazione. *Verifica: flussi completi da browser.* — `routes/carts/+page.svelte` (lista card + form create con modalità/negozio), `lib/components/CartCard.svelte` (rinomina inline + elimina con conferma), voce sidebar `nav.carts`, client `listCarts/getCart/createCart/patchCart/deleteCart/add|removeCartItems`, i18n `carts.*` (en+it).
- [x] **5.F2 — Card del carrello** (~1h): totale pieno barrato, scontato, adjustments, stima finale, provenienza su ogni riga ([layout](../3-features/user/carts.md#la-card-del-carrello)). *Verifica: card conforme al layout.* — `CartCard.svelte`: badge stato (In offerta/Tutto in offerta/Soglia raggiunta + tag "non sano"), voci adjustment con segno, elenco prodotti espandibile (provenienza icona+nome, stato delistato/esaurito, prezzi) con Rimuovi per-riga e "Rimuovi delistati". Flag engine `any_on_sale`/`all_on_sale` aggiunti per i badge.
- [ ] **5.F3 — Soglia con conversione + barra** (~1h): input soglia **in €**, con la **% come comodità di input** nella UI (mostra l'equivalenza "20% ≈ €X" sul totale pieno corrente e invia il valore in €), barra di avvicinamento. *Verifica: barra coerente con lo stato calcolato.*
- [ ] **5.F4 — Selezione dal Product Picker** (~1h): selezione multipla → "aggiungi a carrello **esistente**" (tendina). La **compatibilità multi-scraper** (disabilitare i cart scraper-specific incoerenti) è **rinviata a [6.F0](phase-06-alerts-in-app.md)**: il vincolo resta comunque lato server (5.B2). *Verifica: flusso Picker → carrello fluido con un solo scraper.*

## Definition of Done

- [ ] UC-1 visibile: carrello con adjustments e barra della soglia che riflette i prezzi reali.
- [ ] UC-2 visibile: carrello cross con lo stesso prodotto da fonti diverse, provenienza inequivocabile.
- [ ] Prodotto indisponibile → grigiato, escluso dai totali, soglia in € ricalcolata (esempio normativo CART).
- [ ] [docs](../../docs/) aggiornata in inglese con la sola parte implementata in questa fase (DOC-12).

## Riferimenti

[carts (feature)](../3-features/user/carts.md) · [adjustment (contratto)](../4-capabilities/contracts/adjustment.md)
