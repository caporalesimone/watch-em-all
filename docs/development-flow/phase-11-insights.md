# Fase 11 — Summary, analisi prezzi, export

> Stato: ☐ da iniziare · Prerequisiti: Fasi 7 e 8 · [Indice del flusso](README.md)

## Obiettivo

Il valore "in più" sui dati accumulati: il report periodico, gli indicatori di convenienza (minimo storico, statistiche), l'export dei dati dell'utente.

## Risultato apprezzabile

Ogni lunedì alle 9 arriva il riepilogo dei carrelli; nel grafico di un prodotto leggi "minimo storico €19,90, sconto attuale 20% vs medio 12% — ottimo momento"; quando un ribasso tocca il minimo di sempre, il digest lo dice con un badge dedicato; dal Profilo scarichi tutti i tuoi dati.

## MVP

### Backend

- [ ] **11.B1 — Summary: config e trigger** (~1h): `summary_config` + API, trigger dal worker ([summary-report](../4-capabilities/core/summary-report.md)). *Verifica: trigger solo nei giorni/orario configurati.*
- [ ] **11.B2 — Summary: snapshot e consegna** (~1h): modulo snapshot, consegna sui canali, storico con `kind=summary`, formattazione email nel plugin. *Verifica: report settimanale ricevuto e registrato.*
- [ ] **11.B3 — Statistiche prodotto** (~1h): `product_stats` con medie pesate sul tempo e soglia di significatività ([price-analytics capability](../4-capabilities/core/price-analytics.md)). *Verifica: unit test su storici sintetici (gradini, gap, storico insufficiente).*
- [ ] **11.B4 — API stats + minimo storico** (~1h): `GET /api/products/{id}/stats`, flag `is_all_time_low` nelle righe di catalogo. *Verifica: flag coerente con lo storico.*
- [ ] **11.B5 — Tag minimo storico nell'engine** (~1h): `PRODUCT_ALL_TIME_LOW` nel diff (solo su ribasso), selezionabile per carrello, reso nell'email. *Verifica: ribasso al minimo → tag nel digest; run successiva senza cambi → nessuna ripetizione.*
- [ ] **11.B6 — Indicatore di convenienza** (~1h): euristica a segnali trasparenti nell'endpoint stats ([price-analytics capability](../4-capabilities/core/price-analytics.md)). *Verifica: segnali coerenti con storici sintetici.*
- [ ] **11.B7 — Export JSON** (~1h): `GET /api/me/export?format=json`, secret esclusi ([data-export](../3-features/user/data-export.md)). *Verifica: json fedele ai contratti; nessun campo segreto.*
- [ ] **11.B8 — Export CSV** (~1h): `format=csv` (zip di csv). *Verifica: csv apribili in un foglio di calcolo.*

### Frontend

- [ ] **11.F1 — UI summary nel Profilo** (~1h): on/off, frequenza, giorno, orario. *Verifica: config persistita.*
- [ ] **11.F2 — Pannello statistiche** (~1h): pannello accanto al grafico, stato "storico insufficiente" ([price-analytics feature](../3-features/user/price-analytics.md)). *Verifica: numeri coerenti con lo storico.*
- [ ] **11.F3 — Badge minimo storico** (~1h): badge in Picker, card e grafico. *Verifica: badge coerente col flag.*
- [ ] **11.F4 — Resa dell'indicatore di convenienza** (~1h): etichetta sempre accompagnata dai segnali e dai numeri che la generano. *Verifica: mai la sola etichetta.*
- [ ] **11.F5 — Sezione "I miei dati"** (~1h): download JSON/CSV dal Profilo. *Verifica: download funzionanti da browser.*

## Definition of Done

- [ ] I requisiti ANLZ-R1..R7, EXP-R1..R6 e SUM-R1..R6 verificabili da browser.
- [ ] Con storico insufficiente gli indicatori dicono "storico insufficiente", mai numeri inventati.
- [ ] L'export contiene tutto ciò che l'utente vede nell'app, e nulla che non gli appartenga.
- [ ] [docs-eng](../../docs-eng/) aggiornata in inglese con la sola parte implementata in questa fase (DOC-12).

## Riferimenti

[price-analytics](../3-features/user/price-analytics.md) · [data-export](../3-features/user/data-export.md) · [summary-report (feature)](../3-features/user/summary-report.md)
