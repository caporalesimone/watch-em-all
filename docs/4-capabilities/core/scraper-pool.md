# Scraper Pool (esecuzione controllata)

> **Layer 4 — Capability** · Audience: developer · Pseudocodice ammesso. Feature: [scraper-scheduling-and-limits](../../3-features/admin/scraper-scheduling-and-limits.md), [scraper-monitoring](../../3-features/admin/scraper-monitoring.md).

## Scopo

Eseguire le run degli scraper **in parallelo tra loro** (mai internamente) entro i limiti dell'admin, con lock anti-overlap, timeout, e produzione dei record di monitoraggio. Usato dal worker (run schedulate) e — per lo scrape-now — dal web, che condivide lock e regole.

## Requisiti

- **POOL-R1** — Pool di thread di dimensione `max_concurrent_scrapers` (impostazione di sistema, riletta a caldo). I job oltre il limite attendono in coda FIFO.
- **POOL-R2** — **Lock per-scraper su Postgres** (advisory lock con chiave derivata in modo deterministico dal `plugin_id`): vale tra container (worker e web). Lock non ottenuto = skip con warning, **mai attesa**.
- **POOL-R3** — Un job esegue: apertura `scrape_run` → iterazione utenti (`run_for_user`) con riga `scrape_user_log` per ciascuno → chiusura run con contatori, stato e durata wall-clock.
- **POOL-R4** — **Timeout**: oltre `scraper_run_timeout` il job è terminato e la run marcata `timeout`. Il lock è sempre rilasciato (anche su errore: try/finally; gli advisory lock decadono comunque con la sessione).
- **POOL-R5** — L'errore su un utente non ferma gli altri: la run prosegue e chiude `partial`.
- **POOL-R6** — Il client HTTP del contesto impone il **ritardo di politeness** per-scraper e **conta le richieste** della run (`http_requests`).
- **POOL-R7** — Lo scrape-now (web) esegue un job ridotto a un solo utente, con stessi lock, timeout e record (trigger `manual`).

## Pseudocodice del job

```
def scraper_job(scraper_id, slot, only_user=None, trigger="scheduled"):
    if not try_advisory_lock(scraper_id):
        log_warning("worker", f"{scraper_id}: slot saltato, run precedente in corso")
        return
    try:
        run = open_scrape_run(scraper_id, slot, trigger)
        plugin  = registry.get(scraper_id)
        context = registry.context_for(scraper_id, run)    # http instrumentato per la run
        users   = [only_user] if only_user else plugin.configured_users(context)
        with deadline(settings.scraper_run_timeout):       # POOL-R4
            for user_id in users:
                ulog = open_user_log(run, user_id)
                try:
                    plugin.run_for_user(context, user_id)  # dentro: update_catalog(...)
                    close_user_log(ulog, "ok")
                except Exception as e:
                    close_user_log(ulog, "error", str(e))  # POOL-R5: si prosegue
        close_scrape_run(run, aggregate_status(run), counters(run))
        schedule.set_last_slot(scraper_id, slot)           # anche su partial/error (CRON-R6)
        log_run_outcome(run)                               # info/warning in system_log
    except TimeoutExceeded:
        close_scrape_run(run, "timeout"); schedule.set_last_slot(scraper_id, slot)
        log_error("worker", f"{scraper_id}: run oltre timeout, terminata")
    finally:
        release_advisory_lock(scraper_id)
```

## Contatori della run

| Campo | Fonte |
|---|---|
| `users_processed` | numero di `scrape_user_log` |
| `products_found / new / removed`, `price_changes` | restituiti dal Catalog Update Service per ogni `update_catalog` e sommati |
| `products_excluded` | dichiarati dal plugin (esclusioni specifiche del sito) |
| `http_requests` | client HTTP instrumentato (POOL-R6) |
| durata | `finished_at − started_at` (wall-clock) |

## Note implementative

- La chiave dell'advisory lock è un intero: `hash64(plugin_id)` con hash deterministico (SHA-256 troncato a 8 byte) — mai `hash()` built-in.
- Il deadline è cooperativo dove possibile (cancellazione del client HTTP) con kill del thread come ultima difesa; uno scraper ben scritto muore al primo I/O dopo la cancellazione.
- Il limite del pool si applica anche ai job manuali: uno scrape-now in coda dietro le run schedulate è il comportamento corretto.
