# Scheduling ed esecuzione degli scraper

> **Layer 2 — Architettura** · Audience: architetti SW, system engineer · Testo + Mermaid, niente codice.

## I tre flussi schedulati

Non esiste una cron table unica: i tre flussi hanno owner, granularità e logiche diverse, e sono **deliberatamente disaccoppiati** (lo scrape aggiorna i dati; la notifica arriva quando l'utente la vuole).

| Flusso | Owner | Granularità | Frequenza |
|---|---|---|---|
| **Scrape** | Admin | Per-scraper | **1..N slot al giorno** (lista di orari per scraper) |
| **Alert** | Utente | Per-account | Giorni della settimana scelti + un orario |
| **Summary** | Utente | Per-account | Settimanale (giorno scelto) o mensile (giorno 1), opt-in |

## Il dispatcher (Cron Worker)

Il worker si sveglia ogni minuto e confronta l'ora con gli schedule. Il principio del "dovuto": un job è dovuto quando esiste uno **slot programmato già passato** che non è ancora stato eseguito. Questo dà gratis il **recupero** (catch-up): se il worker era fermo, al riavvio esegue lo slot più recente perso — **uno solo**, mai il replay di tutti gli slot arretrati.

```mermaid
flowchart TD
    T[Tick: ogni minuto] --> S{Per ogni scraper:<br/>ultimo slot dovuto > ultimo eseguito?}
    S -- sì --> POOL[Sottometti al pool<br/>se non già in coda/esecuzione]
    S -- no --> A
    POOL --> A{Per ogni utente:<br/>alert dovuto oggi?}
    A -- sì --> AE[Run Alert Engine]
    A --> SU{Per ogni utente:<br/>summary dovuto?}
    SU -- sì --> SM[Run Summary]
    SU --> HB[Heartbeat + ritorno al tick]
```

Limiti onesti del catch-up (dichiarati, scelta da hobby project):

- **Scraper**: il recupero attraversa la mezzanotte (si confrontano *slot*, non date) — uno scraper fermo dalle 23 recupera lo slot delle 23:50 anche all'1 di notte.
- **Alert e summary**: il recupero vale **entro il giorno dovuto**. Se il sistema resta fermo per l'intera giornata dovuta, quella notifica salta e gli eventi confluiranno nella successiva (il diff è cumulativo per natura: nulla va perso nei contenuti, solo nel momento della consegna).

## Il pool di esecuzione

Gli scraper **non girano nel dispatcher**: vengono sottomessi a un pool di esecuzione che li fa lavorare in parallelo tra loro, entro limiti governati dall'admin.

```mermaid
graph TB
    subgraph "Worker"
        D[Dispatcher<br/>tick al minuto, mai bloccato]
        Q[Coda dei job dovuti]
        subgraph "Pool (max N slot, admin)"
            J1[Job: scraper A<br/>mono-thread]
            J2[Job: scraper B<br/>mono-thread]
        end
    end
    D --> Q --> J1 & J2
```

Regole architetturali (il razionale completo in [3-features/admin/scraper-scheduling-and-limits.md](../3-features/admin/scraper-scheduling-and-limits.md)):

1. **Ogni scraper è intrinsecamente mono-thread**: un solo flusso di lavoro che legge un sito con calma, una richiesta alla volta, con pause configurabili. È una proprietà del contratto, non un'opzione.
2. **Il parallelismo è solo tra scraper diversi** (siti diversi): il pool ne esegue al massimo `N` insieme (`N` configurabile dall'admin, default prudente).
3. **Mai due run dello stesso scraper insieme**: lock per-scraper a livello di database, valido anche tra container (worker e web).
4. **Politeness obbligatoria**: il client HTTP fornito ai plugin impone un ritardo minimo tra richieste allo stesso sito (configurabile per scraper dall'admin). Il sistema **non deve mai** fare flooding o assomigliare a un DoS: poche richieste, lente, identificabili.
5. **Timeout di run**: una run che supera il tempo massimo (admin) viene terminata e marcata in errore — uno scraper appeso non blocca il sistema.

## Osservabilità delle esecuzioni

Ogni run produce un **record di esecuzione** (durata reale, prodotti trovati/nuovi/variati/spariti, richieste HTTP effettuate, esito) con il **dettaglio per utente**; gli eventi operativi (esecuzioni, recuperi, skip per overlap, errori, heartbeat) finiscono nel log di sistema consultabile dall'admin in near-real-time. È la base della [reportistica admin](../3-features/admin/scraper-monitoring.md).

```mermaid
sequenceDiagram
    participant D as Dispatcher
    participant P as Pool
    participant S as Scraper
    participant DB as DB

    D->>P: job (scraper, slot)
    P->>DB: lock per-scraper? sì
    P->>DB: apri scrape_run (slot, trigger)
    loop per ogni utente configurato
        P->>S: run_for_user(utente)
        S->>DB: prodotti via update_catalog
        P->>DB: riga di dettaglio utente
    end
    P->>DB: chiudi scrape_run (esito, contatori, durata)
    P->>DB: rilascia lock + system_log
```

## Assunzioni temporali (V1)

- Granularità al **minuto**; orari confrontati con l'ora del **server**.
- Server e utenti nello **stesso fuso orario** (multi-fuso: [future improvement](../future-improvements/README.md)).
- I cambi ora legale/solare possono spostare di un'ora la percezione di uno slot due volte l'anno: accettato e documentato, nessuna gestione speciale.
