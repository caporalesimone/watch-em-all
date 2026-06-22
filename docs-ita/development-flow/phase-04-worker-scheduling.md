# Fase 4 — Worker e scheduling

> Stato: ☐ da iniziare · Prerequisiti: Fase 3 · [Indice del flusso](README.md)

## Obiettivo

L'automazione: il container worker (sostituisce lo stub di fase 0), gli slot per-scraper (1..N al giorno, indipendenti), il runner seriale con lock e timeout, la cache di scrape con la sua configurazione admin, i record di run e i log osservabili dall'admin.

## Risultato apprezzabile

Imposti "Dragon Store alle 14:30" e alle 14:30 lo scrape parte da solo; nella pagina admin vedi la riga di log, la run con i contatori e il battito del worker. Spegni il worker per un'ora a cavallo dello slot: al riavvio recupera.

## MVP

### Backend

- [ ] **4.B0 — Guardia di disallineamento schema DB (dev)** (~1h): all'avvio confronta il modello ORM (`Base.metadata`) con lo schema reale del DB (`sqlalchemy.inspect`) e segnala **tabelle/colonne mancanti** — `log.warning` per voce + salvataggio su `app.state.schema_drift`. `GET /api/health` espone `schema_drift` (lista) **solo a flag attivo**. Il flag `WEA_SCHEMA_DRIFT_ALERT` è **attivo di default** e si disattiva con `=false` nel `.env` (presente in `.env.example`). Copre **sia le tabelle core (`Base.metadata`) sia quelle dei plugin**: il drift può stare anche su una tabella di plugin (con `MetaData` propria), quindi serve una piccola convenzione per cui **ogni plugin espone la propria `MetaData`** (es. attributo `table_metadata` sulla base plugin, raccolto dal registry) e il check itera core + plugin. Non sostituisce le migrazioni (Alembic non c'è ancora): in dev, per applicare un cambio di schema, resta il reset del volume. **Casi reali che l'hanno motivata (fase 3)**: (1) colonne `brand`/`product_properties` aggiunte alla tabella core `products` → `GET /api/catalog` 500; (2) colonna `name` aggiunta alla tabella **di plugin** `plugin_dragon_store_watches` → `GET /watches` 500 (proprio questo conferma che il check NON può limitarsi alle tabelle core). *Verifica: aggiungo una colonna a un modello (core o plugin) senza ricreare il DB → warning nei log + (flag attivo) `schema_drift` non vuoto su `/api/health`; flag `false` → campo assente.*
- [ ] **4.B1 — Worker reale + heartbeat** (~1h): container `worker` con tick al minuto (sostituisce lo stub 0.T4), heartbeat su file + healthcheck compose ([cron-worker](../4-capabilities/core/cron-worker.md), [deployment](../infrastructure/deployment.md)). *Verifica: heartbeat avanza; kill del worker → container unhealthy.*
- [ ] **4.B2 — Tabella schedule + API** (~1h): `scraper_schedule` (times 1..N, enabled, last_slot), `GET/PUT /api/admin/scrapers/*` ([scheduling-models](../4-capabilities/contracts/scheduling-models.md)). *Verifica: slot salvati e riletti da Swagger.*
- [ ] **4.B3 — latest_due_slot + catch-up** (~1h): calcolo del "dovuto", recupero cross-midnight. *Verifica: unit test tabellari su slot multipli, recupero, mezzanotte.*
- [ ] **4.B4 — Runner seriale** (~1h): esecutore a job singolo con coda FIFO (un solo scraper alla volta, SCHED-R6), errore = slot consumato ([scraper-pool](../4-capabilities/core/scraper-pool.md)). Per ogni utente scrapato **scrive l'anchor `scrape_cooldown`** (mai lo legge, SCR-R15) → subito dopo una run schedulata l'utente non può forzare il manuale. *Verifica: due scraper dovuti allo stesso minuto girano in sequenza; dopo la run schedulata, lo scrape manuale dell'utente è in cooldown.*
- [ ] **4.B5 — Advisory lock + timeout** (~1h): lock per-scraper (condiviso con scrape-now del web), timeout di run. *Verifica: due slot simultanei dello stesso scraper → uno skippa con warning; run oltre timeout → terminata e marcata.*
- [ ] **4.B6 — Record di run** (~1h): `scrape_run` + `scrape_user_log` con contatori (inclusi `http_requests` e `cache_hits` dal client instrumentato). *Verifica: run con due utenti → 1 run + 2 righe utente, contatori sensati.*
- [ ] **4.B7 — Log di sistema** (~1h): `system_log` (heartbeat incluso) + `GET /api/admin/logs?since=<id>` (cursore, filtri). *Verifica: eventi della run presenti e paginati dal cursore.*
- [ ] **4.B8 — Cache di scrape: read-through** (~1h): tabella `scrape_cache`, lettura/scrittura trasparente nel client HTTP del contesto (chiave = richiesta normalizzata per plugin, CTX-R9), contatore `cache_hits`. *Verifica: due utenti con la stessa query nella stessa run → una sola richiesta HTTP.*
- [ ] **4.B9 — Cache: emivita, pulizia, svuotamento** (~1h): scadenza per-plugin, pulizia degli scaduti a inizio run, `DELETE /api/admin/scrapers/{id}/cache`. *Verifica: emivita 0 → nessun riuso; svuotamento → richiesta rifatta.*
- [ ] **4.B10 — Config admin degli scraper** (~1h): tabella `scraper_admin_config` ([schema](../4-capabilities/database/schema.md)) + API admin per le **chiavi riservate del core** (`politeness_delay_s`, `http_timeout_s`, `cache_ttl_min`, **`scrape_now_min_interval_s`** — sostituisce la costante di [3.B11](phase-03-catalog-first-scrape.md)), lette dal contesto a ogni run/scrape (SCR-R15) ([plugin-configuration](../3-features/admin/plugin-configuration.md)). *Verifica: emivita cambiata via API → la run successiva la rispetta, senza riavvio; intervallo Scrape ora cambiato → il prossimo cooldown lo rispetta.*

### Frontend

- [ ] **4.F0 — Banner disallineamento schema (dev)** (~0.5h): legge `schema_drift` da `GET /api/health`; se non vuoto mostra una **barra rossa fissa in basso** con l'elenco delle tabelle/colonne mancanti. Compare solo quando il flag `WEA_SCHEMA_DRIFT_ALERT` è attivo *e* c'è drift. *Verifica: con DB disallineato la barra rossa appare; flag `false` → niente barra.*
- [ ] **4.F1 — Editor degli slot** (~1h): elenco scraper con aggiungi/rimuovi orari e sospensione. *Verifica: slot modificato → la run parte all'orario nuovo.*
- [ ] **4.F2 — Parametri riservati nella pagina admin dello scraper** (~1h): form per politeness, timeout HTTP, emivita cache e **intervallo minimo dello Scrape ora** (le chiavi riservate di 4.B10). *Verifica: modifica da UI → effetto alla run/scrape successiva.*
- [ ] **4.F3 — Pagina Log: polling con cursore** (~1h): lista incrementale near-real-time ([system-logs](../3-features/admin/system-logs-and-maintenance.md)). *Verifica: gli eventi della run appaiono mentre gira.*
- [ ] **4.F4 — Pagina Log: filtri + autoscroll + heartbeat** (~1h): filtri livello/source, auto-scroll pausabile, evidenza heartbeat. *Verifica: filtri applicati al volo; heartbeat visibile.*
- [ ] **4.F5 — Svuota cache** (~1h): pulsante (iniettato dal core per gli scraper, accanto al Test Scraper) che chiama il DELETE della cache, con conferma. *Verifica: dopo lo svuotamento la run successiva rifà le richieste al sito.*

## Definition of Done

- [ ] Scraping quotidiano completamente automatico, **un solo scraper alla volta**, con scrape-now che convive (stessi lock).
- [ ] Scenari di resilienza provati: worker giù sullo slot (recupera), run oltre timeout (terminata e marcata, la coda riparte), errore su un utente (run `partial`).
- [ ] La cache lavora: stessa query tra due utenti o due run entro l'emivita → una sola visita al sito (visibile dai contatori `http_requests`/`cache_hits`); l'emivita si governa dalla UI admin.
- [ ] L'admin risponde a "quando ha girato? com'è andata? quanto ha fatto?" senza guardare il DB.
- [ ] [docs](../../docs/) aggiornata in inglese con la sola parte implementata in questa fase (DOC-12).

## Riferimenti

[scheduling-and-execution](../2-architecture/scheduling-and-execution.md) · [scraper-scheduling-and-limits](../3-features/admin/scraper-scheduling-and-limits.md)
