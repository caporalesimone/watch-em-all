# Log di sistema e manutenzione (admin)

> **Layer 3 — Feature admin** · Audience: architetti, developer · Testo + Mermaid, niente codice.

## Log di sistema

Il registro degli eventi operativi del sistema, consultabile in near-real-time dalla pagina admin (polling incrementale con cursore, auto-scroll pausabile, filtri per livello e origine).

- **LOG-R1** — Origini: `worker` (dispatcher: esecuzioni, recuperi, skip per overlap, heartbeat, manutenzione giornaliera — purge utenti scaduti e relativi errori), `scraper` (eventi emessi dai plugin scraper via logger del contesto), `alert`, `summary`. Livelli: `info`, `warning`, `error`.
- **LOG-R2** — Eventi notevoli sempre registrati: run eseguita (con ritardo rispetto allo slot; oltre soglia → warning "recupero"), slot saltato per overlap (warning), errore/timeout di run (error), heartbeat (info, riga ricorrente).
- **LOG-R3** — Il polling usa un cursore (id dell'ultima riga vista): il server restituisce solo le righe successive.
- **LOG-R4** — I messaggi non contengono mai contenuti operativi degli utenti (titoli dei prodotti, contenuto delle notifiche): solo identificativi e metriche — coerente con il principio che l'admin non legge i dati degli utenti.

## Manutenzione e impostazioni globali

- **MNT-R1** — **Purge dello storico alert**: regola globale per data ("elimina le notifiche di tutti gli utenti precedenti a X / più vecchie di N giorni"), applicata senza accesso ai contenuti.
- **MNT-R2** — **Retention automatica dei log operativi**: log di sistema e record delle run sono puliti automaticamente oltre la finestra configurata (default 90 giorni). Lo **storico prezzi non ha retention**: è il valore del sistema e si conserva per sempre.
- **MNT-R3** — **Impostazioni di sistema** modificabili da UI senza riavvio: `scraper_run_timeout`, soglia di ritardo per i recuperi, giorni di retention, periodo di grazia della cancellazione utenti (`user_deletion_retention_days`). Persistite nel DB (config DB-first), con default sicuri al primo avvio.
- **MNT-R4** — **Salute**: l'app espone un controllo di vita (applicazione + raggiungibilità del DB) usato dal monitoraggio dei container; il worker è sorvegliato tramite heartbeat ([scraper-monitoring](scraper-monitoring.md)).
- **MNT-R5** — **Backup**: script di backup/export/ripristino versionati nel repo (`ops/`) ed eseguibili a mano nel container `db`; l'archivio include dump completo (dati + configurazioni DB-first) e file di bootstrap ([backup-and-restore](../../infrastructure/backup-and-restore.md)). Lo storico prezzi non è ricostruibile: la cadenza la decide chi hosta.

## Vista d'insieme

```mermaid
flowchart LR
    subgraph "Sorgenti"
        W[Worker: run, recuperi,<br/>skip, heartbeat]
        S[Plugin scraper: logger]
        AE[Alert/Summary engine]
    end
    subgraph "Persistenza"
        SL[(Log di sistema)]
        RUNS[(Record delle run)]
    end
    subgraph "Pagina admin"
        LIVE[Log near-real-time<br/>filtri + cursore]
        STATS[Statistiche scraper]
        SET[Impostazioni globali]
        PURGE[Purge storico alert]
    end
    W & S & AE --> SL --> LIVE
    W --> RUNS --> STATS
    RET[Retention automatica] -.pulisce.-> SL & RUNS
    SET -.configura.-> RET
```
