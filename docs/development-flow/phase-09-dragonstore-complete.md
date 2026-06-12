# Fase 9 — Dragon Store completo

> Stato: ☐ da iniziare · Prerequisiti: Fase 4 (e Fase 7 per il valore pieno) · [Indice del flusso](README.md)

## Obiettivo

Portare il primo scraper dal "prodotto singolo" alla configurazione ricca: categorie con paginazione, dedup, esclusioni del sito, UI utente completa con dry-run, e la gestione del ciclo di vita del catalogo (delisting e pulizie).

## Risultato apprezzabile

Incolli l'URL di una categoria, vedi l'anteprima in dry-run, confermi: decine di prodotti entrano nel catalogo a ogni run. I prodotti spariti dal sito si grigiano da soli; li pulisci con un click.

## MVP

### Backend

- [ ] **9.B1 — Riconoscimento URL categoria + fixture** (~1h): pattern `.sp.uw` dalla [pre-analisi](../implemented-plugins/dragon-store/capabilities.md#pre-analisi-del-sito-giugno-2026-una-pagina-di-categoria), fixture di categoria salvate, watch `kind=category`. *Verifica: URL categoria e URL prodotto distinti correttamente.*
- [ ] **9.B2 — Parsing delle card di categoria** (~1h): estrazione dalle card `resultBox.prod` (titolo, prezzi, id, disponibilità). *Verifica: test verdi sulle fixture di categoria.*
- [ ] **9.B3 — Paginazione delle categorie** (~1h): attraversamento delle pagine su categorie grandi, una richiesta alla volta (chiude DRG-Q4). *Verifica: categoria reale multi-pagina → tutti i prodotti.*
- [ ] **9.B4 — Dedup con priorità** (~1h): priorità categoria su prodotto singolo (DRG-R3). *Verifica: input sovrapposti → zero duplicati.*
- [ ] **9.B5 — Filtro ammaccati per-categoria** (~1h): flag `include_ammaccati` per watch di categoria (default false, filtro via prefisso del titolo, esclusi conteggiati in `products_excluded`); prodotti singoli mai filtrati e "l'inclusione vince" (DRG-R4/R7/R8). *Verifica: stesso ammaccato escluso da una categoria e incluso da un'altra → consegnato.*
- [ ] **9.B6 — Delisting end-to-end** (~1h): `removed` nel delta attivato end-to-end, riattivazione se il prodotto ricompare. *Verifica: prodotto tolto dalla fixture → `removed`; ricompare → riattivato.*
- [ ] **9.B7 — Pulizie catalogo** (~1h): endpoint rimuovi-delistati / selettiva / svuota, con cascate dichiarate. *Verifica: cascate corrette su carrelli e storico.*

### Frontend

- [ ] **9.F1 — Lista watches completa** (~1h): input attivi con tipo, conteggi e stato del toggle ammaccati; rimozione ([features](../implemented-plugins/dragon-store/features.md)). *Verifica: lista fedele allo stato del plugin.*
- [ ] **9.F2 — Aggiunta con riconoscimento + toggle ammaccati** (~1h): riconoscimento automatico del tipo di URL, toggle **"Includi ammaccati"** per le categorie (default off, modificabile dopo), **avviso in rosso** sull'anteprima di un prodotto singolo AMMACCATO. *Verifica: toggle riflesso nell'anteprima.*
- [ ] **9.F3 — Dry-run delle categorie** (~1h): anteprima con la tabella risultati condivisa, conteggi inclusi/esclusi. *Verifica: flusso anteprima → conferma → entry.*
- [ ] **9.F4 — Pulizie catalogo nel Picker** (~1h): righe delistate grigiate, azioni "rimuovi delistati" / modalità delete / svuota con conferme che dichiarano le cascate ([catalog feature](../3-features/user/catalog-and-product-picker.md)). *Verifica: conferme esplicite, tabella coerente dopo ogni azione.*

## Definition of Done

- [ ] Monitoraggio per categoria operativo nelle run schedulate, con contatori coerenti nel monitoring.
- [ ] I punti aperti DRG-Q1..Q7 risolti o aggiornati nella doc del plugin.
- [ ] Idempotenza confermata anche con categorie (seconda run senza cambi → zero delta).
- [ ] [docs-eng](../../docs-eng/) aggiornata in inglese con la sola parte implementata in questa fase (DOC-12).

## Riferimenti

[Dragon Store](../implemented-plugins/dragon-store/overview.md) · [scraper-plugin (contratto)](../3-features/plugins/scraper-plugin.md)
