# Scraper Runner (esecuzione seriale)

> **Layer 4 — Capability** · Audience: developer · Pseudocodice ammesso. Feature: [scraper-scheduling-and-limits](../../3-features/admin/scraper-scheduling-and-limits.md), [scraper-monitoring](../../3-features/admin/scraper-monitoring.md).

## Scopo

Eseguire le run degli scraper **una alla volta** (nessuna concorrenza tra scraper, né interna), con lock anti-overlap, timeout, pulizia della cache scaduta e produzione dei record di monitoraggio. Usato dal worker (run schedulate) e — per lo scrape-now — dal web, che condivide lock e regole.

## Requisiti

- **POOL-R1** — **Esecutore seriale**: un singolo thread di esecuzione; i job dovuti attendono in **coda FIFO** e girano uno alla volta (SCHED-R6). Nessun parametro di parallelismo.
- **POOL-R2** — **Lock per-scraper su Postgres** (advisory lock con chiave derivata in modo deterministico dal `plugin_id`): vale tra container (worker e web — la serialità della coda copre il worker; il lock copre gli scrape on-demand del web). Lock non ottenuto = skip con warning, **mai attesa**.
- **POOL-R3** — Un job esegue: pulizia della **cache scaduta** del plugin (CTX-R9) → apertura `scrape_run` → iterazione utenti (`run_for_user`) con riga `scrape_user_log` per ciascuno → chiusura run con contatori, stato e durata wall-clock.
- **POOL-R4** — **Timeout**: oltre `scraper_run_timeout` il job è terminato e la run marcata `timeout`. Il lock è sempre rilasciato (anche su errore: try/finally; gli advisory lock decadono comunque con la sessione). Con l'esecuzione seriale il timeout è anche la protezione della coda: un job appeso non deve trattenere i successivi.
- **POOL-R5** — L'errore su un utente non ferma gli altri: la run prosegue e chiude `partial`.
- **POOL-R6** — Il client HTTP del contesto impone il **ritardo di politeness** per-scraper, serve dalla **cache di scrape** le richieste ripetute (CTX-R9) e **conta** richieste reali (`http_requests`) e riusi (`cache_hits`) della run, attribuendoli anche all'utente in lavorazione (la run è mono-thread: un utente alla volta).
- **POOL-R7** — Lo scrape-now (web) esegue un job ridotto a un solo utente, con stessi lock, timeout e record (trigger `manual`).

## Pseudocodice del job

```
def scraper_job(scraper_id, slot, only_user=None, trigger="scheduled"):
    if not try_advisory_lock(scraper_id):
        log_warning("worker", f"{scraper_id}: slot saltato, run precedente in corso")
        return
    try:
        cache.purge_expired(scraper_id)                    # POOL-R3 / CTX-R9
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
| `http_requests` | client HTTP instrumentato (POOL-R6): solo richieste **reali** al sito; contato anche per-utente su `scrape_user_log` |
| `cache_hits` | richieste servite dalla cache di scrape senza toccare il sito (CTX-R9); contato anche per-utente |
| durata | `finished_at − started_at` (wall-clock) |

## Note implementative

- La chiave dell'advisory lock è un intero: `hash64(plugin_id)` con hash deterministico (SHA-256 troncato a 8 byte) — mai `hash()` built-in.
- Il deadline è cooperativo dove possibile (cancellazione del client HTTP) con kill del thread come ultima difesa; uno scraper ben scritto muore al primo I/O dopo la cancellazione.
- La serialità vale anche per i job manuali del worker; uno scrape-now partito dal **web** gira nel proprio container e si coordina col solo lock per-scraper (limite dichiarato: può sovrapporsi alla run schedulata di un *altro* scraper — evento raro, un job una tantum a catalogo vuoto).
