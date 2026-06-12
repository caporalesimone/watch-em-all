# Cron Worker (dispatcher)

> **Layer 4 — Capability** · Audience: developer · Pseudocodice ammesso. Feature: [scheduling-and-execution](../../2-architecture/scheduling-and-execution.md), [scraper-scheduling-and-limits](../../3-features/admin/scraper-scheduling-and-limits.md).

## Scopo

Processo del container `worker` che fa da **dispatcher temporale**: ogni minuto valuta i tre schedule e sottomette i job dovuti; una volta al giorno esegue la **manutenzione** (purge utenti scaduti, retention). **Non esegue mai lavoro lungo nel proprio loop**: gli scraper vanno al [runner seriale](scraper-pool.md); alert e summary sono run brevi eseguite inline.

## Requisiti

- **CRON-R1** — Tick ogni minuto; granularità al minuto.
- **CRON-R2** — **Scraper**: per ogni scraper abilitato calcola l'**ultimo slot dovuto** (il più recente orario programmato ≤ now, anche di ieri) e lo confronta con l'ultimo slot eseguito: se più recente → accoda il job al runner. Il recupero attraversa la mezzanotte; si recupera **solo lo slot più recente** perso.
- **CRON-R3** — **Alert**: dovuto se oggi è un giorno scelto, `now ≥ orario` e non già eseguito oggi. Recupero entro il giorno dovuto (oltre, salta: scelta dichiarata).
- **CRON-R4** — **Summary**: come alert, con regola weekly (giorno scelto) / monthly (giorno 1).
- **CRON-R5** — Il dispatcher **non si blocca mai**: l'accodamento al runner è asincrono; i job in coda escono uno alla volta (esecuzione seriale, SCHED-R6).
- **CRON-R6** — Il marcatore di esecuzione (slot/data) viene aggiornato **anche in caso di errore** della run: niente retry-storm al minuto successivo; il prossimo slot è il retry naturale. L'errore è registrato.
- **CRON-R7** — **Heartbeat**: a ogni tick il worker tocca il proprio heartbeat (riga dedicata + file locale per l'healthcheck del container).
- **CRON-R8** — Tutti gli eventi (esecuzioni, recuperi oltre soglia, skip per overlap, errori) vanno in `system_log` con i source documentati ([system-logs](../../3-features/admin/system-logs-and-maintenance.md)).
- **CRON-R9** — Il worker assume di essere **a replica singola** (vincolo dichiarato): i check dovuto/eseguito non sono progettati per più dispatcher concorrenti. I lock per-scraper proteggono comunque dalle esecuzioni on-demand concorrenti del web.
- **CRON-R10** — **Manutenzione giornaliera**: al primo tick di ogni nuovo giorno il worker esegue, inline e in quest'ordine: (1) il **purge degli utenti scaduti** — per ogni account con `deletion_due_at ≤ now`, plugin prima e core dopo (USR-R9/R10); un fallimento lascia l'utente in cancellazione e si ritenta il giorno successivo; (2) la **retention** di `system_log` e dei record di run (MNT-R2). Esiti in `system_log` (source `worker`); la guardia anti-doppione è una data di ultima manutenzione persistita, come per alert e summary.

## Pseudocodice del tick

```
def tick(now):
    heartbeat(now)                                   # CRON-R7

    # --- MANUTENZIONE: una volta al giorno (CRON-R10) ---
    if maintenance.last_run_date < now.date():
        purge_expired_users(now)                      # deletion_due_at <= now: plugin poi core (USR-R10)
        apply_retention(now)                          # system_log + scrape_run/scrape_user_log (MNT-R2)
        maintenance.last_run_date = now.date()        # anche su errore parziale: si ritenta domani

    # --- SCRAPER: slot multipli per giorno, recupero cross-midnight ---
    for s in scraper_schedules where s.enabled:
        slot = latest_due_slot(s.times, now)          # max slot datetime <= now (oggi o ieri)
        if slot is not None and slot > s.last_slot:
            runner.submit(scraper_job(s.scraper_id, slot))  # non blocca; il runner è seriale: lock + coda FIFO

    # --- ALERT: per-utente, giorni della settimana ---
    for a in alert_schedules where a.weekdays:
        if now.weekday() in a.weekdays and now.time() >= a.time and a.last_run_date < now.date():
            try: alert_engine.run(a.user_id)
            except Exception as e: log_error("alert", a.user_id, e)
            a.last_run_date = now.date()              # sempre, anche su errore (CRON-R6)

    # --- SUMMARY: weekly/monthly ---
    for c in summary_configs where c.enabled:
        if summary_due(c, now) and c.last_run_date < now.date():
            try: summary.run(c.user_id)
            except Exception as e: log_error("summary", c.user_id, e)
            c.last_run_date = now.date()

def latest_due_slot(times, now) -> datetime | None:
    # times = ["06:00", "14:00", "22:00"]; considera oggi e ieri
    candidates = [combine(d, t) for d in (today, yesterday) for t in times]
    passed = [c for c in candidates if c <= now]
    return max(passed) if passed else None

def summary_due(c, now) -> bool:
    day_ok = (c.frequency == "weekly" and now.weekday() == c.weekday) \
          or (c.frequency == "monthly" and now.day == 1)
    return day_ok and now.time() >= c.time
```

Il confronto su **slot** (datetime, non solo data) per gli scraper è ciò che fa funzionare il recupero a cavallo di mezzanotte e gli N slot al giorno; `last_slot` è persistito su `scraper_schedule`.

## Ritardo e soglia di recupero

`ritardo = now − slot`. Se supera la soglia configurata (impostazioni di sistema), l'evento è loggato come **recupero** a livello `warning`; sotto soglia è una normale esecuzione `info`. Gli **skip per overlap** (lock già preso al momento dell'esecuzione del job) sono `warning`: ripetuti, indicano uno scraper troppo lento per i suoi slot.

## Interfacce

| Direzione | Cosa |
|---|---|
| Legge | `scraper_schedule`, `alert_schedule`, `summary_config`, `users` (scadenze di cancellazione), impostazioni di sistema |
| Scrive | `last_slot` / `last_run_date`, `system_log`, heartbeat; purge utenti scaduti e retention (manutenzione giornaliera) |
| Invoca | [Scraper Runner](scraper-pool.md) (submit), [Alert Engine](alert-engine.md), [Summary](summary-report.md), `delete_user_data` dei plugin (purge, USR-R10) |
