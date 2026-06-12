# Fase 8 — Grafici dello storico

> Stato: ☐ da iniziare · Prerequisiti: Fase 5 (i dati si accumulano dalla Fase 3) · [Indice del flusso](README.md)

## Obiettivo

Rendere visibile il tesoro che il sistema accumula da settimane: le serie dello storico prezzi, con i gap di disponibilità, per prodotto e per carrello.

## Risultato apprezzabile

Dal Product Picker apri il grafico di un prodotto: linea a gradini del prezzo, buchi dove era esaurito, selettori Week/Month/All. Dalla card del carrello, l'andamento del totale.

## MVP

### Backend

- [ ] **8.B1 — Serie prodotto** (~2h): `GET /api/products/{id}/history?range=` a gradini con flag disponibilità, inclusa l'entry-prima-del-range ([price-history capability](../4-capabilities/core/price-history.md)). *Verifica: serie corretta su fixture con gap.*
- [ ] **8.B2 — Serie carrello** (~2h): somma a gradini della composizione corrente (semplificazione HIST-R4), `GET /api/carts/{id}/history`. *Verifica: il totale della serie "oggi" coincide col totale della card.*

### Frontend

- [ ] **8.F1 — Componente grafico** (~4h): **unico componente** del design system: gradini, gap espliciti, selettori, tooltip (data, prezzo, disponibilità), entrambi i temi. *Verifica: vista prodotto conforme a [price-history (feature)](../3-features/user/price-history.md).*
- [ ] **8.F2 — Pagina Storico prezzi + accessi** (~3h): navigazione per prodotto e per carrello (stesso componente), accesso dal Product Picker e dalla card del carrello. *Verifica: pagina completa da sidebar e dai punti di accesso.*

## Definition of Done

- [ ] Grafici fluidi su storici reali accumulati dalle fasi precedenti.
- [ ] Un solo componente grafico nel codice (due sorgenti dati).
- [ ] Il gap di indisponibilità è visibile e non interpolato.
- [ ] [docs-eng](../../docs-eng/) aggiornata in inglese con la sola parte implementata in questa fase (DOC-12).

## Riferimenti

[price-history (feature)](../3-features/user/price-history.md) · [price-history (capability)](../4-capabilities/core/price-history.md)
