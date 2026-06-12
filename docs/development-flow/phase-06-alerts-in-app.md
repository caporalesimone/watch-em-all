# Fase 6 — Alert in-app

> Stato: ☐ da iniziare · Prerequisiti: Fasi 4 e 5 · [Indice del flusso](README.md)

## Obiettivo

Il motore delle notifiche, consegnate per ora solo **in-app**: baseline, diff, digest aggregato, storico con stato di lettura, cadenza per-utente. Il canale esterno arriva nella fase 7 — separarli rende ciascuna fase piccola e verificabile.

## Risultato apprezzabile

Attivi gli alert su un carrello, un prezzo cambia, e all'orario scelto trovi nello Storico alert un digest leggibile: cosa è cambiato, prezzi prima/dopo, provenienza, stato soglia. Badge "non letto" in dashboard.

## MVP

### Backend

- [ ] **6.B1 — Tipi di alert per carrello** (~1h): `cart_alert_types` (presenza=abilitato), `PUT /api/carts/{id}/alert-types`. *Verifica: selezione persistita via Swagger.*
- [ ] **6.B2 — Baseline** (~3h): `alert_snapshot` per-(utente,carrello), seed/delete sugli eventi utente (primo tipo abilitato, tutti disabilitati, cadenza on/off) ([alert-engine — baseline](../4-capabilities/core/alert-engine.md#la-baseline)). *Verifica: abilita → riga snapshot; disabilita → sparita.*
- [ ] **6.B3 — Alert Engine** (~4h): diff completo (tag prodotto con prezzi, eventi carrello, soglia con guardia zero-attivi), `AlertEvent`, scrittura `alert_log`. Unit test sui casi normativi (prima run silenziosa, sceso-e-risalito, ulteriore ribasso, parziale). *Verifica: test verdi sulla [tabella dei casi](../4-capabilities/core/alert-engine.md#casi-normativi).*
- [ ] **6.B4 — Cadenza utente** (~2h): `alert_schedule` + API, trigger dal worker con recupero intra-day. *Verifica: run solo nei giorni/orario dovuti.*
- [ ] **6.B5 — API storico alert** (~1h): elenco paginato, dettaglio, letto/non letto, unread-count. *Verifica: da Swagger.*

### Frontend

- [ ] **6.F1 — UI tipi di alert sulla card** (~1h): selezione per carrello con avviso sugli effetti baseline ("il monitoraggio riparte da ora"). *Verifica: selezione → baseline coerente.*
- [ ] **6.F2 — UI cadenza nel Profilo** (~2h): picker giorni L–D + orario, con avviso sull'effetto off→baseline. *Verifica: cadenza salvata e rispettata.*
- [ ] **6.F3 — Storico alert UI** (~3h): elenco paginato, dettaglio digest, stato letto/non letto, badge in dashboard. *Verifica: flusso completo da browser.*

## Definition of Done

- [ ] Scenario completo: abilita alert → scrape cambia un prezzo → all'orario di cadenza il digest è nello storico, una sola notifica per quanti carrelli ci siano.
- [ ] Nessuna ripetizione: run successiva senza cambi → nessuna notifica.
- [ ] Il digest contiene tutto per decidere (ALERT-R7): prezzi, provenienza, soglia.
- [ ] [docs-eng](../../docs-eng/) aggiornata in inglese con la sola parte implementata in questa fase (DOC-12).

## Riferimenti

[notification-architecture](../2-architecture/notification-architecture.md) · [alerts-and-notifications](../3-features/user/alerts-and-notifications.md) · [alert-event (contratto)](../4-capabilities/contracts/alert-event.md)
