# Fase 11 — Summary, analisi prezzi, export

> Stato: ☐ da iniziare · Prerequisiti: Fasi 7 e 8 · [Indice del flusso](README.md)

## Obiettivo

Il valore "in più" sui dati accumulati: il report periodico, gli indicatori di convenienza (minimo storico, statistiche), l'export dei dati dell'utente.

## Risultato apprezzabile

Ogni lunedì alle 9 arriva il riepilogo dei carrelli; nel grafico di un prodotto leggi "minimo storico €19,90, sconto attuale 20% vs medio 12% — ottimo momento"; quando un ribasso tocca il minimo di sempre, il digest lo dice con un badge dedicato; dal Profilo scarichi tutti i tuoi dati.

## MVP

### Backend

- [ ] **11.B1 — Summary report** (~3h): `summary_config` + API, modulo snapshot, trigger dal worker, consegna sui canali e storico con `kind=summary` ([summary-report](../4-capabilities/core/summary-report.md)); formattazione email del summary nel plugin. *Verifica: report settimanale ricevuto e registrato.*
- [ ] **11.B2 — Statistiche prodotto** (~3h): `product_stats` con medie pesate sul tempo e soglia di significatività, `GET /api/products/{id}/stats`, flag `is_all_time_low` nelle righe di catalogo ([price-analytics capability](../4-capabilities/core/price-analytics.md)). *Verifica: unit test su storici sintetici (gradini, gap, storico insufficiente).*
- [ ] **11.B3 — Tag minimo storico nell'engine** (~2h): `PRODUCT_ALL_TIME_LOW` nel diff dell'Alert Engine (solo su ribasso), selezionabile per carrello, reso nell'email. *Verifica: ribasso al minimo → tag nel digest; run successiva senza cambi → nessuna ripetizione.*
- [ ] **11.B4 — Indicatore di convenienza** (~2h): euristica a segnali trasparenti nell'endpoint stats ([price-analytics capability](../4-capabilities/core/price-analytics.md)). *Verifica: segnali coerenti con storici sintetici.*
- [ ] **11.B5 — Export dati** (~3h): `GET /api/me/export?format=json|csv` (zip per csv), secret esclusi ([data-export](../3-features/user/data-export.md)). *Verifica: json fedele ai contratti; csv apribili in un foglio di calcolo; nessun campo segreto.*

### Frontend

- [ ] **11.F1 — UI summary nel Profilo** (~1h): on/off, frequenza, giorno, orario. *Verifica: config persistita.*
- [ ] **11.F2 — Pannello statistiche + badge** (~3h): pannello accanto al grafico, badge "Minimo storico" in Picker/card/grafico, stato "storico insufficiente" ([price-analytics feature](../3-features/user/price-analytics.md)). *Verifica: badge e numeri coerenti con lo storico.*
- [ ] **11.F3 — Resa dell'indicatore di convenienza** (~1h): etichetta sempre accompagnata dai segnali e dai numeri che la generano. *Verifica: mai la sola etichetta.*
- [ ] **11.F4 — Sezione "I miei dati"** (~1h): download JSON/CSV dal Profilo. *Verifica: download funzionanti da browser.*

## Definition of Done

- [ ] I requisiti ANLZ-R1..R7, EXP-R1..R6 e SUM-R1..R6 verificabili da browser.
- [ ] Con storico insufficiente gli indicatori dicono "storico insufficiente", mai numeri inventati.
- [ ] L'export contiene tutto ciò che l'utente vede nell'app, e nulla che non gli appartenga.

## Riferimenti

[price-analytics](../3-features/user/price-analytics.md) · [data-export](../3-features/user/data-export.md) · [summary-report (feature)](../3-features/user/summary-report.md)
