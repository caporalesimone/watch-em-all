# Fase 4 — Worker e scheduling

> Stato: ☐ da iniziare · Prerequisiti: Fase 3 · [Indice del flusso](README.md)

## Obiettivo

L'automazione: il container worker, gli slot per-scraper (1..N al giorno), il pool con lock e timeout, i record di run e i log osservabili dall'admin.

## Risultato apprezzabile

Imposti "Dragon Store alle 14:30" e alle 14:30 lo scrape parte da solo; nella pagina admin vedi la riga di log, la run con i contatori e il battito del worker. Spegni il worker per un'ora a cavallo dello slot: al riavvio recupera.

## MVP

### Backend

- [ ] **4.B1 — Worker + heartbeat** (~2h): container `worker`, tick al minuto, heartbeat (file + `system_log`), healthcheck compose ([cron-worker](../4-capabilities/core/cron-worker.md), [deployment](../infrastructure/deployment.md)). *Verifica: heartbeat avanza; kill del worker → container unhealthy.*
- [ ] **4.B2 — Schedule a slot + catch-up** (~3h): `scraper_schedule` (times 1..N, enabled, last_slot), `latest_due_slot`, recupero cross-midnight, `GET/PUT /api/admin/scrapers/*`. Unit test tabellari del "dovuto". *Verifica: test su slot multipli, recupero, mezzanotte.*
- [ ] **4.B3 — Pool con lock e timeout** (~4h): thread pool `max_concurrent_scrapers`, advisory lock per-scraper (condiviso con scrape-now del web), timeout di run, errore = slot consumato ([scraper-pool](../4-capabilities/core/scraper-pool.md)). *Verifica: due slot simultanei dello stesso scraper → uno skippa con warning.*
- [ ] **4.B4 — Record di run** (~3h): `scrape_run` + `scrape_user_log` con contatori (incluso `http_requests` dal client instrumentato) ([scheduling-models](../4-capabilities/contracts/scheduling-models.md)). *Verifica: run con due utenti → 1 run + 2 righe utente, contatori sensati.*
- [ ] **4.B5 — Log di sistema** (~2h): `system_log` + `GET /api/admin/logs?since=<id>` (cursore, filtri). *Verifica: eventi della run presenti e paginati dal cursore.*

### Frontend

- [ ] **4.F1 — UI scheduler admin minima** (~2h): elenco scraper con editor degli slot (aggiungi/rimuovi orari) e sospensione. *Verifica: slot modificato → la run parte all'orario nuovo.*
- [ ] **4.F2 — Pagina Log di sistema** (~2h): polling incrementale con cursore, filtri livello/source, auto-scroll pausabile, evidenza heartbeat ([system-logs](../3-features/admin/system-logs-and-maintenance.md)). *Verifica: gli eventi della run appaiono in near-real-time.*

## Definition of Done

- [ ] Scraping quotidiano completamente automatico, con scrape-now che convive (stessi lock).
- [ ] Scenari di resilienza provati: worker giù sullo slot (recupera), run oltre timeout (terminata e marcata), errore su un utente (run `partial`).
- [ ] L'admin risponde a "quando ha girato? com'è andata? quanto ha fatto?" senza guardare il DB.

## Riferimenti

[scheduling-and-execution](../2-architecture/scheduling-and-execution.md) · [scraper-scheduling-and-limits](../3-features/admin/scraper-scheduling-and-limits.md)
