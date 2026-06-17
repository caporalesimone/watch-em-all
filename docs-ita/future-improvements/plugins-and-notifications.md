# Future Improvements — Plugin e notifiche

> Formato: cosa · perché rimandato · trigger di promozione.

## Notifier Telegram

Bot Telegram come canale (config admin: token del bot; config utente: chat id con flusso di pairing). **Rimandato perché**: email e Discord coprono i primi utenti; il contratto notifier è già pronto a riceverlo. **Trigger**: primo utente che lo chiede.

## Notifier Webhook generico

POST del payload JSON a un URL dell'utente: il canale "per smanettoni" che abilita qualunque integrazione (Home Assistant, ntfy, script propri). Costo di sviluppo minimo. **Trigger**: primo caso d'uso di automazione.

## Alert istantanei (post-scrape)

Oggi gli alert escono solo alla cadenza scelta. **Miglioria**: opzione per-carrello "avvisami subito" valutata a fine scrape (con throttling anti-flood), per le offerte lampo. **Rimandato perché**: complica il modello a baseline (diff per-scrape vs per-cadenza) e i casi d'uso primari reggono bene la cadenza quotidiana. **Trigger**: occasioni perse documentate per ritardo di notifica.

## Routing per tipo di evento

"Le soglie via email, la disponibilità su Discord". **Rimandato perché**: matrice di config che quintuplica i casi senza valore ai numeri attuali. **Trigger**: richiesta reale motivata.

## Dedup del fetch tra utenti

Due utenti che osservano la stessa categoria = doppio scraping (catalogo per-utente, scelta di isolamento). **Miglioria**: cache di fetch per-run dentro il plugin (stessa URL scaricata una volta, fan-out sugli utenti) — nessun cambio di contratto. **Trigger**: run visibilmente gonfiate da sovrapposizioni (visibile dal monitoraggio: `http_requests` vs utenti).

## Marketplace / plugin di terze parti

Oggi i plugin sono first-party fidati (trust model dichiarato). Plugin di terzi richiederebbero sandboxing reale (processi separati, permessi DB per plugin), review di sicurezza, firma. **Rimandato perché**: sproporzionato. **Trigger**: il progetto smette di essere personale.

## Suite di scraping condivisa

Helper comuni per pattern ricorrenti (paginazione standard, parsing prezzi/valute, retry su markup instabile) estratti dai primi 2-3 scraper reali. **Trigger**: terzo scraper con codice duplicato evidente.
