# Contratti — Modelli di scheduling e monitoraggio

> **Layer 4 — Contratto** · Audience: developer · Pseudocodice ammesso. Feature: [scraper-scheduling-and-limits](../../3-features/admin/scraper-scheduling-and-limits.md), [scraper-monitoring](../../3-features/admin/scraper-monitoring.md).

Tre schedule con owner diversi più le impostazioni globali, letti dal dispatcher; le run schedulate degli scraper producono i record di esecuzione:

```mermaid
flowchart TB
    subgraph ADM["Admin"]
        SS[ScraperSchedule<br/>times[], enabled, last_slot]
        SET[SystemSettings<br/>timeout · retention · grazia cancellazione]
    end
    subgraph USR["Per-utente"]
        AS[AlertSchedule<br/>weekdays, time, last_run_date]
        SC[SummaryConfig<br/>weekly/monthly, last_run_date]
    end
    CRON[Cron Worker<br/>tick/min] --> SS & AS & SC
    SS --> REC[ScrapeRun + ScrapeUserLog<br/>record di esecuzione]
```

## Schedule

```python
# Scrape — admin, per-scraper, 1..N slot al giorno
class ScraperSchedule(BaseModel):
    scraper_id: str                    # = plugin_id dello scraper
    times: list[str]                   # 1..N orari (slot) canonici "HH:MM:SS" (4.F1); input
                                       # accettato "HH:MM" o "HH:MM:SS"; ordinati, unici
    enabled: bool = True               # sospensione runtime senza toccare il manifest
    last_slot: datetime | None = None  # ultimo slot ESEGUITO (datetime, non date:
                                       # regge N slot/giorno e il recupero cross-midnight)

# Alert — per-utente: cadenza calendariale
class AlertSchedule(BaseModel):
    user_id: int
    scheduled_time: time
    weekdays: list[int] = []           # 0=lun..6=dom (convenzione Python date.weekday();
                                       # ⚠ JS Date.getDay() parte da domenica: la UI mappa)
                                       # [] = off · 7 giorni = giornaliera
    last_run_date: date | None = None  # guardia anti-doppione + recupero intra-day

# Summary — per-utente: vedi SummaryConfig in core/summary-report.md
```

## Impostazioni di sistema (admin, runtime)

```python
class SystemSettings(BaseModel):       # persistite in system_settings (key-value), editabili da UI
    scraper_run_timeout_min: int = 30  # oltre → run terminata, stato "timeout"
    catchup_warning_min: int = 10      # ritardo oltre cui un'esecuzione è loggata come recupero
    log_retention_days: int = 90       # system_log + scrape_run/scrape_user_log
    user_deletion_retention_days: int = 30  # periodo di grazia prima del purge automatico (USR-R9);
                                       # la scadenza è fissata alla marcatura: cambi solo pro-futuro
```

## Record di esecuzione (monitoraggio)

```python
class ScrapeRun(BaseModel):            # UNA riga per run di scraper
    run_id: int
    scraper_id: str
    trigger: Literal["scheduled", "manual"]    # manual = scrape-now
    slot: datetime | None              # lo slot programmato (None se manual)
    started_at: datetime
    finished_at: datetime | None
    status: Literal["running", "ok", "partial", "error", "timeout"]
    # ok = tutti gli utenti ok · partial = almeno un utente ok e uno fallito
    # error = nessun utente completato · timeout = terminata dal sistema
    users_processed: int
    products_found: int
    products_new: int
    price_changes: int
    products_removed: int
    products_excluded: int             # esclusioni decise dal plugin (NON gli out-of-stock)
    http_requests: int                 # contate dal client del core (solo richieste reali al sito)
    cache_hits: int                    # richieste servite dalla cache di scrape (CTX-R9)
    error_message: str | None

class ScrapeUserLog(BaseModel):        # UNA riga per utente per run
    run_id: int
    user_id: int
    started_at: datetime
    finished_at: datetime | None
    products_found: int
    products_new: int
    price_changes: int
    http_requests: int                 # quota della run attribuita a questo utente
    cache_hits: int                    # idem, riusi dalla cache
    status: Literal["ok", "error"]
    error_message: str | None
```

Note normative:

- La **durata della run** è `finished_at − started_at` del record di run (wall-clock), mai la somma dei tempi per-utente.
- Il dettaglio per-utente è la base del drill-down admin ("chi genera il carico").
- Retention: `scrape_run`/`scrape_user_log` e `system_log` seguono `log_retention_days`; gli schedule no.
