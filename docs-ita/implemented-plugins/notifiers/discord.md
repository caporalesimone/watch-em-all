# Discord — Notifier

> **Implemented plugin** · Tipo: notifier · Stato: **pianificato (placeholder)** — cartella presente con `enabled: false`, implementazione futura. Contratto generico: [notifier-plugin](../../3-features/plugins/notifier-plugin.md).

## Cosa farà

Consegna digest e summary su **Discord** tramite **webhook di canale**: l'utente crea un webhook sul proprio server/canale Discord e ne incolla l'URL nel Profilo. Scelto il webhook (e non un bot) per semplicità: niente token di bot, niente presenza permanente, zero config admin.

## Configurazione prevista

| Livello | Campi | Note |
|---|---|---|
| **Admin** | — (nessuna infrastruttura di sistema) | il canale è subito "disponibile" |
| **Utente** | `webhook_url` (url, required, secret) + flag attivo | con bottone Test |

## Formattazione prevista

- **Digest**: un messaggio con **embed per carrello** — titolo del carrello, campi per prodotto (tag come emoji/badge, prezzo prima → dopo, provenienza, link), colore dell'embed in base all'evento più rilevante (soglia raggiunta = evidenza).
- **Summary**: embed riepilogativo per carrello.
- Limiti Discord (lunghezza embed/campi): troncamento con "e altri N…" e link allo storico in-app.

## Errori e retry

Webhook eliminato/non valido (404): errore permanente, niente retry, messaggio chiaro all'utente. Rate limit Discord (429): rispetto dell'header `Retry-After`, max 3 tentativi.

## Punti aperti

| ID | Punto |
|---|---|
| DSC-Q1 | Un messaggio per digest o un messaggio per carrello? (default proposto: uno per digest, embed multipli) |
| DSC-Q2 | Mostrare le thumbnail dei prodotti negli embed? |
