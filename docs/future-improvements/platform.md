# Future Improvements — Piattaforma e infrastruttura

> Formato: cosa · perché rimandato · trigger di promozione.

## Multi-timezone

Gli orari (slot scraper, cadenze alert) sono confrontati con l'ora del server; si assume che server e utenti condividano il fuso. **Miglioria**: timezone per-utente sul profilo, schedule valutati nel fuso dell'utente; gestione DST esplicita. **Rimandato perché**: installazione casalinga, utenti nello stesso fuso. **Trigger**: il primo utente in un fuso diverso.

## Multi-lingua

La V1 è **English-only**, ma l'impalcatura i18n è obbligatoria fin dal primo giorno (chiavi di traduzione ovunque, file di lingua, `users.locale` nello schema, lingua passata ai notifier). **Miglioria in due stadi**: (1) *statico* — tradurre i file di lingua di core e plugin (UI, etichette dei digest, default dei messaggi di sistema) ed esporre il selettore lingua nel profilo: solo traduzione, zero refactor; (2) *dinamico* — un servizio di traduzione innestato nella cucitura documentata della pipeline dei messaggi testuali ([admin-notifications](../3-features/admin/admin-notifications.md)), per tradurre override e messaggi admin nella lingua di ogni destinatario: l'unità è la coppia (testo, lingua), si traducono solo le lingue presenti tra i destinatari, i placeholder si riempiono dopo la traduzione. **Rimandato perché**: utenti attuali anglofoni/italofoni a proprio agio con l'inglese; un traduttore dinamico di qualità richiede un servizio esterno. **Trigger**: il primo utente che chiede l'interfaccia in italiano (stadio 1); insoddisfazione per i messaggi admin monolingua (stadio 2).

## TLS nativo / esposizione a Internet di default

Oggi: HTTP su LAN, TLS delegato a un reverse proxy opzionale. **Miglioria**: guida completa di hardening per l'esposizione (proxy con TLS automatico, rate limiting al proxy, fail2ban). **Rimandato perché**: l'uso primario è LAN. **Trigger**: esposizione stabile a Internet.

## Logout per-dispositivo e sessioni visibili

`token_version` è per-utente: il logout invalida tutti i dispositivi. **Miglioria**: refresh jti per-device con elenco sessioni attive e revoca selettiva. **Rimandato perché**: con utenti singoli su 1-2 device il logout globale è indolore. **Trigger**: lamentele reali sul logout globale.

## Versioning delle API (`/api/v2/`)

Un solo client (la SPA della stessa release): nessuna esigenza di compatibilità. **Trigger**: un client esterno reale (app mobile, script di terzi) costruito sulle API.

## Scaling del worker (repliche multiple)

Il dispatcher assume replica singola (CRON-R9); i lock per-scraper già reggono la concorrenza con il web. **Miglioria**: lock estesi ai flussi alert/summary e dispatcher idempotente per N repliche. **Rimandato perché**: a ≤5 utenti un worker basta e avanza. **Trigger**: decine di scraper con slot fitti che saturano la coda seriale.

## Esecuzione parallela tra scraper

Il runner è **seriale** per scelta (SCHED-R6): un solo scraper alla volta, carico prevedibile, vista calendario fedele. **Miglioria**: reintrodurre un pool con limite di parallelismo configurabile (la storia del progetto lo conosce già). **Rimandato perché**: a poche decine di run al giorno la serialità non costa nulla e semplifica tutto. **Trigger**: la vista calendario non ha più spazi liberi — gli slot dovuti si accodano sistematicamente oltre l'orario utile.

## Auto-update delle installazioni

Le immagini versionate su GHCR e il deploy kit esistono già ([deployment](../infrastructure/deployment.md), INF-17); l'aggiornamento resta però manuale (`WEA_VERSION` + `pull`). **Miglioria**: aggiornamento automatico con watchtower o equivalente. **Rimandato perché**: su un'installazione personale l'update va scelto, non subìto. **Trigger**: più installazioni da mantenere che restano indietro di versione.
