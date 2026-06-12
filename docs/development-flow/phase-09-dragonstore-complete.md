# Fase 9 — Dragon Store completo

> Stato: ☐ da iniziare · Prerequisiti: Fase 4 (e Fase 7 per il valore pieno) · [Indice del flusso](README.md)

## Obiettivo

Portare il primo scraper dal "prodotto singolo" alla configurazione ricca: categorie con paginazione, dedup, esclusioni del sito, UI utente completa con dry-run, e la gestione del ciclo di vita del catalogo (delisting e pulizie).

## Risultato apprezzabile

Incolli l'URL di una categoria, vedi l'anteprima in dry-run, confermi: decine di prodotti entrano nel catalogo a ogni run. I prodotti spariti dal sito si grigiano da soli; li pulisci con un click.

## MVP

### Backend

- [ ] **9.B1 — Categorie + paginazione** (~4h): riconoscimento categoria dal pattern URL `.sp.uw` ([pre-analisi](../implemented-plugins/dragon-store/capabilities.md#pre-analisi-del-sito-giugno-2026-una-pagina-di-categoria)), parsing delle card `resultBox.prod`, verifica della paginazione su categorie grandi (chiude DRG-Q4), fixture salvate. *Verifica: categoria reale → tutti i prodotti, una richiesta alla volta.*
- [ ] **9.B2 — Dedup + filtro ammaccati per-categoria** (~2h): priorità categoria su prodotto singolo (DRG-R3); flag `include_ammaccati` per watch di categoria (default false, filtro via prefisso del titolo, esclusi conteggiati in `products_excluded`); prodotti singoli mai filtrati e "l'inclusione vince" (DRG-R4/R7/R8). *Verifica: input sovrapposti → zero duplicati; stesso ammaccato escluso da una categoria e incluso da un'altra → consegnato.*
- [ ] **9.B3 — Delisting end-to-end** (~2h): `removed` nel delta attivato end-to-end, endpoint di pulizia catalogo (rimuovi delistati / selettiva / svuota) con cascate. *Verifica: prodotto tolto dalla fixture → `removed`; ricompare → riattivato.*

### Frontend

- [ ] **9.F1 — UI utente del plugin** (~4h): pagina watches (lista input attivi con tipo, conteggi e stato del toggle ammaccati; aggiunta con riconoscimento automatico; rimozione), toggle **"Includi ammaccati"** per le categorie (default off, modificabile dopo), **avviso in rosso** sull'anteprima di un prodotto singolo AMMACCATO, dry-run con la tabella condivisa ([features](../implemented-plugins/dragon-store/features.md)). *Verifica: flusso anteprima → conferma → entry; toggle riflesso nell'anteprima.*
- [ ] **9.F2 — Pulizie catalogo nel Picker** (~2h): righe delistate grigiate, azioni "rimuovi delistati" / modalità delete / svuota con conferme che dichiarano le cascate ([catalog feature](../3-features/user/catalog-and-product-picker.md)). *Verifica: conferme esplicite, tabella coerente dopo ogni azione.*

## Definition of Done

- [ ] Monitoraggio per categoria operativo nelle run schedulate, con contatori coerenti nel monitoring.
- [ ] I punti aperti DRG-Q1..Q7 risolti o aggiornati nella doc del plugin.
- [ ] Idempotenza confermata anche con categorie (seconda run senza cambi → zero delta).
- [ ] [docs-eng](../../docs-eng/) aggiornata in inglese con la sola parte implementata in questa fase (DOC-12).

## Riferimenti

[Dragon Store](../implemented-plugins/dragon-store/overview.md) · [scraper-plugin (contratto)](../3-features/plugins/scraper-plugin.md)
