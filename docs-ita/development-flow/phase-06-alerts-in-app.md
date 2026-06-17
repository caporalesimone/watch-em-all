# Fase 6 — Alert in-app

> Stato: ☐ da iniziare · Prerequisiti: Fasi 4 e 5 · [Indice del flusso](README.md)

## Obiettivo

Il motore delle notifiche, consegnate per ora solo **in-app**: baseline, diff, digest aggregato, storico con stato di lettura, cadenza per-utente. Il canale esterno arriva nella fase 7 — separarli rende ciascuna fase piccola e verificabile.

## Risultato apprezzabile

Attivi gli alert su un carrello, un prezzo cambia, e all'orario scelto trovi nello Storico alert un digest leggibile: cosa è cambiato, prezzi prima/dopo, provenienza, stato soglia. Badge "non letto" in dashboard.

## MVP

### Backend

- [ ] **6.B1 — Tipi di alert per carrello** (~1h): `cart_alert_types` (presenza=abilitato), `PUT /api/carts/{id}/alert-types`. *Verifica: selezione persistita via Swagger.*
- [ ] **6.B2 — Baseline: seed** (~1h): `alert_snapshot` per-(utente,carrello), seed al primo tipo abilitato ([alert-engine — baseline](../4-capabilities/core/alert-engine.md#la-baseline)). *Verifica: abilita → riga snapshot con lo stato corrente.*
- [ ] **6.B3 — Baseline: transizioni** (~1h): delete su tutti-disabilitati e cadenza off, re-seed su cadenza on. *Verifica: disabilita → snapshot sparita; riattiva → "il monitoraggio riparte da ora".*
- [ ] **6.B4 — Diff prodotti** (~1h): tag prodotto con prezzi prima/dopo, prima run silenziosa ([alert-engine](../4-capabilities/core/alert-engine.md)). *Verifica: unit test sui casi normativi (prima run, sceso-e-risalito, ulteriore ribasso).*
- [ ] **6.B5 — Diff carrello + soglia** (~1h): eventi carrello, soglia con guardia zero-attivi, run parziale. *Verifica: unit test sui [casi normativi](../4-capabilities/core/alert-engine.md#casi-normativi).*
- [ ] **6.B6 — AlertEvent + alert_log** (~1h): costruzione dell'`AlertEvent` aggregato (un digest per utente, non per carrello) e scrittura in `alert_log` ([alert-event](../4-capabilities/contracts/alert-event.md)). *Verifica: due carrelli con cambi → un solo digest.*
- [ ] **6.B7 — Cadenza utente** (~1h): `alert_schedule` + API, trigger dal worker con recupero intra-day. *Verifica: run solo nei giorni/orario dovuti; worker giù sull'orario → recupera in giornata.*
- [ ] **6.B8 — API storico alert** (~1h): elenco paginato, dettaglio, letto/non letto, unread-count. *Verifica: da Swagger.*

### Frontend

- [ ] **6.F1 — UI tipi di alert sulla card** (~1h): selezione per carrello con avviso sugli effetti baseline ("il monitoraggio riparte da ora"). *Verifica: selezione → baseline coerente.*
- [ ] **6.F2 — UI cadenza nel Profilo** (~1h): picker giorni L–D + orario, con avviso sull'effetto off→baseline. *Verifica: cadenza salvata e rispettata.*
- [ ] **6.F3 — Storico alert: elenco + dettaglio** (~1h): lista paginata, dettaglio digest leggibile. *Verifica: digest completo da browser.*
- [ ] **6.F4 — Letto/non letto + badge** (~1h): stato di lettura, badge unread in dashboard. *Verifica: lettura → badge aggiornato.*

## Definition of Done

- [ ] Scenario completo: abilita alert → scrape cambia un prezzo → all'orario di cadenza il digest è nello storico, una sola notifica per quanti carrelli ci siano.
- [ ] Nessuna ripetizione: run successiva senza cambi → nessuna notifica.
- [ ] Il digest contiene tutto per decidere (ALERT-R7): prezzi, provenienza, soglia.
- [ ] [docs](../../docs/) aggiornata in inglese con la sola parte implementata in questa fase (DOC-12).

## Riferimenti

[notification-architecture](../2-architecture/notification-architecture.md) · [alerts-and-notifications](../3-features/user/alerts-and-notifications.md) · [alert-event (contratto)](../4-capabilities/contracts/alert-event.md)
