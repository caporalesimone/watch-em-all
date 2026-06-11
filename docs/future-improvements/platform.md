# Future Improvements — Piattaforma e infrastruttura

> Formato: cosa · perché rimandato · trigger di promozione.

## Multi-timezone

Gli orari (slot scraper, cadenze alert) sono confrontati con l'ora del server; si assume che server e utenti condividano il fuso. **Miglioria**: timezone per-utente sul profilo, schedule valutati nel fuso dell'utente; gestione DST esplicita. **Rimandato perché**: installazione casalinga, utenti nello stesso fuso. **Trigger**: il primo utente in un fuso diverso.

## TLS nativo / esposizione a Internet di default

Oggi: HTTP su LAN, TLS delegato a un reverse proxy opzionale. **Miglioria**: guida completa di hardening per l'esposizione (proxy con TLS automatico, rate limiting al proxy, fail2ban). **Rimandato perché**: l'uso primario è LAN. **Trigger**: esposizione stabile a Internet.

## Logout per-dispositivo e sessioni visibili

`token_version` è per-utente: il logout invalida tutti i dispositivi. **Miglioria**: refresh jti per-device con elenco sessioni attive e revoca selettiva. **Rimandato perché**: con utenti singoli su 1-2 device il logout globale è indolore. **Trigger**: lamentele reali sul logout globale.

## Versioning delle API (`/api/v2/`)

Un solo client (la SPA della stessa release): nessuna esigenza di compatibilità. **Trigger**: un client esterno reale (app mobile, script di terzi) costruito sulle API.

## Scaling del worker (repliche multiple)

Il dispatcher assume replica singola (CRON-R9); i lock per-scraper già reggono la concorrenza con il web. **Miglioria**: lock estesi ai flussi alert/summary e dispatcher idempotente per N repliche. **Rimandato perché**: a ≤5 utenti un worker basta e avanza. **Trigger**: decine di scraper con slot fitti che saturano il pool.

## Auto-update / immagini pubblicate

Oggi il deploy è `git pull && build`. **Miglioria**: immagini versionate su un registry + watchtower o equivalente. **Trigger**: più di una installazione da mantenere.
