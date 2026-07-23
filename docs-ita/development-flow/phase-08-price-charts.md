# Fase 8 — Grafici dello storico

> Stato: 🚧 in corso (avviata 2026-07-23) · Prerequisiti: Fase 5 (i dati si accumulano dalla Fase 3) · [Indice del flusso](README.md)

> **❓ Punto da chiarire (annotato 2026-07-23).** Serve una soluzione per **gestire i prodotti delisted (`removed`)**: oggi si **accumulano nel DB** e non esiste un modo per eliminarli. Da **discutere a livello di UX** varie proposte — es. pulizia manuale "rimuovi delistati", auto-purge dopo N giorni, nascondi-di-default con toggle "mostra delistati", retention configurabile dall'admin, … La Fase 9 introduce già endpoint di pulizia catalogo (9.B7) e le azioni nel Picker (9.F4) **per Dragon Store**; qui si tratta di decidere la **strategia/UX generale e trasversale** (quale comportamento di default, dove si agisce, cosa cascata su carrelli/storico).

## Obiettivo

Rendere visibile il tesoro che il sistema accumula da settimane: le serie dello storico prezzi, con i gap di disponibilità, per prodotto e per carrello.

## Risultato apprezzabile

Dal Product Picker apri il grafico di un prodotto: linea a gradini del prezzo, buchi dove era esaurito, selettori Week/Month/All. Dalla card del carrello, l'andamento del totale.

## MVP

### Backend

- [x] **8.B1 — Serie prodotto** (~1h): `GET /api/products/{id}/history?range=` a gradini con flag disponibilità, inclusa l'entry-prima-del-range ([price-history capability](../4-capabilities/core/price-history.md)). *Verifica: serie corretta su fixture con gap.*
- [x] **8.B2 — Serie carrello** (~1h): somma a gradini della composizione corrente (semplificazione HIST-R4), `GET /api/carts/{id}/history`. *Verifica: il totale della serie "oggi" coincide col totale della card.*

### Frontend

- [ ] **8.F1 — Componente grafico: gradini e gap** (~1h): linea a gradini, gap di disponibilità espliciti e non interpolati — **un componente unico** del design system. **Mock**: alimentato da una serie statica finché non è collegato (8.F3). *Verifica: resa conforme a [price-history (feature)](../3-features/user/price-history.md) sulla serie di prova.*
- [ ] **8.F2 — Componente grafico: range, tooltip, temi** (~1h): selettori Week/Month/All, tooltip (data, prezzo, disponibilità), entrambi i temi. *Verifica: interazioni fluide nei due temi.*
- [ ] **8.F3 — Pagina Storico prezzi** (~1h): navigazione per prodotto e per carrello (stesso componente, due sorgenti dati reali). *Verifica: pagina completa da sidebar.*
- [ ] **8.F4 — Accessi dal Picker e dalla card** (~1h): apertura del grafico dal Product Picker e dalla card del carrello. *Verifica: i punti di accesso portano al grafico giusto.*

## Definition of Done

- [ ] Grafici fluidi su storici reali accumulati dalle fasi precedenti.
- [ ] Un solo componente grafico nel codice (due sorgenti dati).
- [ ] Il gap di indisponibilità è visibile e non interpolato.
- [ ] [docs](../../docs/) aggiornata in inglese con la sola parte implementata in questa fase (DOC-12).

## Riferimenti

[price-history (feature)](../3-features/user/price-history.md) · [price-history (capability)](../4-capabilities/core/price-history.md)
