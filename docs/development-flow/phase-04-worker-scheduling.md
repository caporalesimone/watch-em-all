# Fase 4 — Worker e scheduling

> Stato: ☐ da iniziare · Prerequisiti: Fase 3 · [Indice del flusso](README.md)

## Obiettivo

L'automazione: il container worker, gli slot per-scraper (1..N al giorno, indipendenti), il runner seriale con lock e timeout, la cache di scrape, i record di run e i log osservabili dall'admin.

## Risultato apprezzabile

Imposti "Dragon Store alle 14:30" e alle 14:30 lo scrape parte da solo; nella pagina admin vedi la riga di log, la run con i contatori e il battito del worker. Spegni il worker per un'ora a cavallo dello slot: al riavvio recupera.

## MVP

### Backend

- [ ] **4.B1 — Worker + heartbeat** (~2h): container `worker`, tick al minuto, heartbeat (file + `system_log`), healthcheck compose ([cron-worker](../4-capabilities/core/cron-worker.md), [deployment](../infrastructure/deployment.md)). *Verifica: heartbeat avanza; kill del worker → container unhealthy.*
- [ ] **4.B2 — Schedule a slot + catch-up** (~3h): `scraper_schedule` (times 1..N, enabled, last_slot), `latest_due_slot`, recupero cross-midnight, `GET/PUT /api/admin/scrapers/*`. Unit test tabellari del "dovuto". *Verifica: test su slot multipli, recupero, mezzanotte.*
- [ ] **4.B3 — Runner seriale con lock e timeout** (~3h): esecutore a job singolo con coda FIFO (un solo scraper alla volta, SCHED-R6), advisory lock per-scraper (condiviso con scrape-now del web), timeout di run, errore = slot consumato ([scraper-pool](../4-capabilities/core/scraper-pool.md)). *Verifica: due scraper dovuti allo stesso minuto girano in sequenza; due slot simultanei dello stesso scraper → uno skippa con warning.*
- [ ] **4.B4 — Record di run** (~3h): `scrape_run` + `scrape_user_log` con contatori (inclusi `http_requests` e `cache_hits` dal client instrumentato) ([scheduling-models](../4-capabilities/contracts/scheduling-models.md)). *Verifica: run con due utenti → 1 run + 2 righe utente, contatori sensati.*
- [ ] **4.B5 — Log di sistema** (~2h): `system_log` + `GET /api/admin/logs?since=<id>` (cursore, filtri). *Verifica: eventi della run presenti e paginati dal cursore.*
- [ ] **4.B6 — Cache di scrape** (~3h): tabella `scrape_cache`, read-through trasparente nel client HTTP del contesto (chiave = richiesta normalizzata per plugin, emivita per-plugin, CTX-R9), pulizia degli scaduti a inizio run, `DELETE /api/admin/scrapers/{id}/cache`, contatore `cache_hits`. *Verifica: due utenti con la stessa query nella stessa run → una sola richiesta HTTP; emivita 0 → nessun riuso; svuotamento → richiesta rifatta.*

### Frontend

- [ ] **4.F1 — UI scheduler admin minima** (~2h): elenco scraper con editor degli slot (aggiungi/rimuovi orari) e sospensione. *Verifica: slot modificato → la run parte all'orario nuovo.*
- [ ] **4.F2 — Pagina Log di sistema** (~2h): polling incrementale con cursore, filtri livello/source, auto-scroll pausabile, evidenza heartbeat ([system-logs](../3-features/admin/system-logs-and-maintenance.md)). *Verifica: gli eventi della run appaiono in near-real-time.*
- [ ] **4.F3 — Svuota cache nella pagina admin del plugin** (~1h): pulsante (iniettato dal core per gli scraper, accanto al Test Scraper) che chiama il DELETE della cache, con conferma. *Verifica: dopo lo svuotamento la run successiva rifà le richieste al sito.*

## Definition of Done

- [ ] Scraping quotidiano completamente automatico, **un solo scraper alla volta**, con scrape-now che convive (stessi lock).
- [ ] Scenari di resilienza provati: worker giù sullo slot (recupera), run oltre timeout (terminata e marcata, la coda riparte), errore su un utente (run `partial`).
- [ ] La cache lavora: stessa query tra due utenti o due run entro l'emivita → una sola visita al sito (visibile dai contatori `http_requests`/`cache_hits`).
- [ ] L'admin risponde a "quando ha girato? com'è andata? quanto ha fatto?" senza guardare il DB.
- [ ] [docs-eng](../../docs-eng/) aggiornata in inglese con la sola parte implementata in questa fase (DOC-12).

## Riferimenti

[scheduling-and-execution](../2-architecture/scheduling-and-execution.md) · [scraper-scheduling-and-limits](../3-features/admin/scraper-scheduling-and-limits.md)
