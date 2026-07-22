# Fase 6 — Alert in-app

> Stato: ✅ implementata (2026-07-22) — in attesa di merge PR + release `0.6.0` · Prerequisiti: Fasi 4 e 5 · [Indice del flusso](README.md)

## Obiettivo

Il motore delle notifiche, consegnate per ora solo **in-app**: baseline, diff, digest aggregato, storico con stato di lettura, cadenza per-utente. Il canale esterno arriva nella fase 7 — separarli rende ciascuna fase piccola e verificabile.

## Risultato apprezzabile

Attivi gli alert su un carrello, un prezzo cambia allo scrape successivo, e **subito** trovi nello Storico alert un digest leggibile: cosa è cambiato, prezzi prima/dopo, provenienza, stato soglia. Badge "non letto" in dashboard. Nessuna cadenza da configurare: gli alert sono **event-driven** (scattano a fine scrape).

## ✅ Riconciliato a inizio fase (docs-ita ↔ codice)

> Discrepanze emerse alla chiusura della Fase 5 (mirror inglese DOC-12), **risolte** all'apertura della Fase 6. Punti 1, 2, 4, 5: l'inglese era già allineato al codice, quindi i doc italiani implementati sono stati **migrati in inglese e rimossi** (grande migrazione doc di inizio fase). Punto 3: la rotta `alert-types` è stata implementata in **6.B1** col contratto documentato; `ThresholdInfo` in `alert-event.md` (spec-ahead) è stato allineato al modello € (via `pct`, aggiunti `reached`/`partial`). Sezione lasciata come storico.

1. **`Adjustment` — modello a 4 campi.** [`adjustment.md`](../../docs/4-capabilities/contracts/adjustment.md) mostra solo `description` + `amount`; il codice ([`src/core/contracts.py`](../../src/core/contracts.py)) ha **4 campi**: `id` (chiave i18n completa, resa dal frontend), `description` (**solo-debug**), `amount` (con segno), `params` (interpolazione i18n). L'esempio IT (`description="Sconto soglia 100"` come se fosse user-facing) è fuorviante → allineare al modello deciso in 5.B3/5.B5.
2. **`get_adjustments` — firma a 2 argomenti.** Lo pseudocodice IT (in `adjustment.md` e [`cart-engine.md`](../../docs/4-capabilities/core/cart-engine.md)) usa `get_adjustments(cart_total)`; il codice reale (base + Dragon + call-site dell'engine) è `get_adjustments(products, cart_total)` → allineare.
3. **`endpoints.md` IT — rotte non ancora implementate.** Elenca `PUT /api/carts/{id}/alert-types` e `GET /api/carts/{id}/history`, assenti in Fase 5 (giustamente esclusi dal mirror EN). Sono **contratto spec-ahead** (regola di flusso #8): la *alert-types* la implementa **6.B1**, la *history* è Fase 8 → nessuna correzione doc, solo **verificare** che il contratto documentato è quello giusto quando li implementiamo.
4. **`CartState` — flag non documentati in IT.** L'engine implementato espone anche `has_delisted`, `any_on_sale`, `all_on_sale` e `currency`, che le "Definizioni" IT di `cart-engine.md` non citano → arricchire `cart-engine.md`.
5. **Adjustments Dragon — valori dell'esempio.** L'esempio IT usa spedizione generica **−€7**; le regole reali ([`adjustments.py`](../../src/plugins/scrapers/dragon_store/backend/adjustments.py)) sono spedizione **−€5, gratis ≥€100** e sconti **5/10/15% a €100/200/300**. L'esempio IT è illustrativo, ma conviene usare i valori reali per coerenza.

## MVP

### Da gestire per prima (rinviato dalla Fase 5)

- [x] **6.F0 — Product Picker → carrello: compatibilità multi-scraper** (~1h): nella tendina "aggiungi a carrello" della selezione multipla, un carrello **scraper-specific** è selezionabile solo se il suo scraper coincide con il plugin di **tutti** i prodotti selezionati (i **cross** sempre); selezione che copre più scraper → gli scraper-specific incompatibili appaiono disabilitati con una nota. Rinviato dalla Fase 5 (5.F4) per provare prima la UX di base con un solo scraper; il vincolo lato server (uno scraper-specific rifiuta prodotti di altri scraper) è già attivo dalla 5.B2. *Verifica: con prodotti di due scraper selezionati, solo i cart cross e i cart dello scraper coerente sono selezionabili.*

### Backend

- [x] **6.B1 — Tipi di alert per carrello** (~1h): `cart_alert_types` (presenza=abilitato), `PUT /api/carts/{id}/alert-types`. *Verifica: selezione persistita via Swagger.*
- [x] **6.B2 — Baseline: seed** (~1h): `alert_snapshot` per-(utente,carrello), seed al primo tipo abilitato ([alert-engine — baseline](../4-capabilities/core/alert-engine.md#la-baseline)). *Verifica: abilita → riga snapshot con lo stato corrente.*
- [x] **6.B3 — Baseline: transizioni** (~1h): seed all'abilitazione del primo tipo, delete quando si disabilitano tutti. *Verifica: disabilita tutti → snapshot sparita.*
- [x] **6.B4 — Diff prodotti** (~1h): tag prodotto con prezzi prima/dopo, prima run silenziosa ([alert-engine](../4-capabilities/core/alert-engine.md)). *Verifica: unit test sui casi normativi (prima run, sceso-e-risalito, ulteriore ribasso).*
- [x] **6.B5 — Diff carrello + soglia** (~1h): eventi carrello, soglia con guardia zero-attivi, run parziale. *Verifica: unit test sui [casi normativi](../4-capabilities/core/alert-engine.md#casi-normativi).*
- [x] **6.B6 — AlertEvent + alert_log** (~1h): costruzione dell'`AlertEvent` aggregato (un digest per utente, non per carrello) e scrittura in `alert_log` ([alert-event](../4-capabilities/contracts/alert-event.md)). *Verifica: due carrelli con cambi → un solo digest.*
- [x] **6.B7 — Trigger event-driven** (~1h): il motore alert gira **a fine scrape** per gli utenti toccati — worker (scrape schedulato) + web (scrape-now, "Simula scraping" del TP), via `adjust.run_user_alerts`. **Cadenza a orario RIMOSSA** (niente `alert_schedule`/API). *Verifica: dopo uno scrape con cambi → digest scritto; test event-driven end-to-end.*
- [x] **6.B8 — API storico alert** (~1h): elenco paginato, dettaglio, letto/non letto, unread-count. *Verifica: da Swagger.*

### Frontend

- [x] **6.F1 — UI tipi di alert sulla card** (~1h): selezione per carrello con avviso sugli effetti baseline ("il monitoraggio riparte da ora"). *Verifica: selezione → baseline coerente.*
- [x] **6.F2 — (rimosso)** — la UI cadenza nel Profilo è stata **eliminata** con il passaggio a event-driven: non c'è più nulla da configurare (niente giorni/orario). La scelta *quali* tipi di alert resta sulla card del carrello (6.F1).
- [x] **6.F3 — Storico alert: elenco + dettaglio** (~1h): lista paginata, dettaglio digest leggibile. *Verifica: digest completo da browser.*
- [x] **6.F4 — Letto/non letto + badge** (~1h): stato di lettura, badge unread in sidebar **aggiornato live** (poll 20s), tag di prodotto resi come badge localizzati (AEV-R3), **eliminazione multipla** degli alert dallo storico (`DELETE /api/alerts`). *Verifica: lettura → badge aggiornato; nuovo alert → badge cambia entro 20s; selezione + elimina.*

## Definition of Done

- [x] Scenario completo: abilita alert → scrape cambia un prezzo → **a fine scrape** il digest è nello storico, una sola notifica per quanti carrelli ci siano.
- [x] Nessuna ripetizione: run successiva senza cambi → nessuna notifica.
- [x] Il digest contiene tutto per decidere (ALERT-R7): prezzi, provenienza, soglia.
- [x] [docs](../../docs/) aggiornata in inglese con la sola parte implementata in questa fase (DOC-12).

## Riferimenti

[notification-architecture](../2-architecture/notification-architecture.md) · [alerts-and-notifications](../3-features/user/alerts-and-notifications.md) · [alert-event (contratto)](../4-capabilities/contracts/alert-event.md)
