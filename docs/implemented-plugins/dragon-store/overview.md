# Dragon Store — Overview

> **Implemented plugin** · Tipo: scraper · Sito: `dragonstore.it` · Primo scraper del sistema, riferimento per i futuri.

## Cosa fa

Monitora prezzi e disponibilità dei prodotti su `dragonstore.it` (giochi da tavolo, carte collezionabili e affini). È un'implementazione concreta dello [Scraper Plugin](../../3-features/plugins/scraper-plugin.md): tutta la conoscenza del sito — input accettati, navigazione per categorie, paginazione, stati speciali dei prodotti, regole di sconto — è interna al plugin; il core riceve solo `Product`.

## Per chi

L'utente tipo è il collezionista del caso d'uso [UC-1](../../1-business/use-cases.md): tiene d'occhio una wishlist sul negozio e compra in blocco quando il risparmio complessivo (sconti a soglia inclusi) lo soddisfa.

## In sintesi

| Aspetto | Scelta |
|---|---|
| Input dell'utente | URL di **prodotto singolo** e URL di **categoria** (enumerata con paginazione) |
| Esclusioni del sito | prodotti **"ammaccati"** (danneggiati): esclusi **di default**, includibili con un toggle **per categoria**; un ammaccato aggiunto come prodotto singolo è sempre incluso (scelta esplicita, segnalata in rosso in UI) |
| Out-of-stock | inclusi con `is_available=false` (contratto) |
| Adjustments | **sconti a soglia** sul totale del carrello (regole del negozio), configurabili dall'admin |
| Identità prodotto | **ID numerico nativo** del sito (presente negli URL `.gp.<id>.uw` e nelle card) — verificato in pre-analisi, vedi [capabilities](capabilities.md) |
| Strategia tecnica | pagine **server-rendered** (classic ASP): HTTP + parsing HTML, niente browser headless — pre-analisi, da confermare |

## Caratteristiche note del sito

- Pagine di listing **server-rendered** con prezzi e disponibilità già nell'HTML; AJAX solo per ordinamenti e cambi vista (pre-analisi: vedi [capabilities](capabilities.md)).
- Prodotti in stati speciali ("ammaccato") pubblicati come **schede distinte** con prefisso nel titolo e prezzo ridotto: esclusi di default dal monitoraggio, includibili su scelta dell'utente (per categoria, o aggiungendoli esplicitamente come prodotto singolo).
- Regole di sconto a soglia sul totale del carrello (es. −10% sopra 50 €, −15% sopra 100 €).

## Documenti

| Documento | Contenuto |
|---|---|
| [features.md](features.md) | Comportamento dettagliato: input, UI utente/admin, dedup, filtri |
| [capabilities.md](capabilities.md) | Tabelle, flusso di run, strategia di scraping, punti aperti |
