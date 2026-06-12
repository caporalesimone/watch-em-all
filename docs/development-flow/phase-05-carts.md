# Fase 5 — Carrelli

> Stato: ☐ da iniziare · Prerequisiti: Fase 3 (la 4 può procedere in parallelo) · [Indice del flusso](README.md)

## Obiettivo

Il cuore funzionale: carrelli nelle due modalità, totali calcolati, adjustments, soglia. Da qui in poi i due [use case](../1-business/use-cases.md) si vedono a schermo.

## Risultato apprezzabile

Crei "Wishlist giochi" (scraper-specific): la card mostra totale pieno barrato, scontato, lo sconto a soglia di Dragon Store, la stima finale e la barra verso la tua soglia. Crei "Fotocamera" (cross) con lo stesso prodotto da più watch: ogni riga mostra il suo negozio.

## MVP

### Backend

- [ ] **5.B1 — Modello e CRUD** (~3h): tabelle `carts`/`cart_members` (UNIQUE, cascate), API CRUD + membri ([endpoints](../api/endpoints.md#carrelli--cart-engine)), regole modalità (immutabile; scraper-specific accetta solo prodotti del suo scraper). *Verifica: vincoli rispettati via Swagger.*
- [ ] **5.B2 — Cart Engine** (~3h): attivi/esclusi, totali, soglia % (conversione da assoluto, confronto sulla stima finale, niente soglia senza attivi) ([cart-engine](../4-capabilities/core/cart-engine.md)). Unit test tabellari incluso il ricalcolo su indisponibilità. *Verifica: test verdi sui casi normativi di [carts.md](../3-features/user/carts.md).*
- [ ] **5.B3 — Adjustments Dragon Store** (~2h): `get_adjustments` con soglie configurabili, integrazione nel calcolo ([dragon-store features](../implemented-plugins/dragon-store/features.md)). *Verifica: carrello sopra soglia → voce di sconto nello stato calcolato.*

### Frontend

- [ ] **5.F1 — UI carrelli** (~4h): pagina con card complete ([layout](../3-features/user/carts.md#la-card-del-carrello)), creazione/modifica/eliminazione, soglia con conversione mostrata. *Verifica: card conforme al layout, provenienza su ogni riga.*
- [ ] **5.F2 — Selezione dal Product Picker** (~2h): selezione multipla → "aggiungi a carrello". *Verifica: flusso Picker → carrello fluido.*

## Definition of Done

- [ ] UC-1 visibile: carrello con adjustments e barra della soglia che riflette i prezzi reali.
- [ ] UC-2 visibile: carrello cross con lo stesso prodotto da fonti diverse, provenienza inequivocabile.
- [ ] Prodotto indisponibile → grigiato, escluso dai totali, soglia in € ricalcolata (esempio normativo CART).
- [ ] [docs-eng](../../docs-eng/) aggiornata in inglese con la sola parte implementata in questa fase (DOC-12).

## Riferimenti

[carts (feature)](../3-features/user/carts.md) · [adjustment (contratto)](../4-capabilities/contracts/adjustment.md)
