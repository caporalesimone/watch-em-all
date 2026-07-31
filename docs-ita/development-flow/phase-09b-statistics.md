# Fase 9b — Statistics

> Stato: 💡 da dettagliare · Prerequisiti: Fase 9 (che raccoglie i dati) · [Indice del flusso](README.md)
>
> **Annotata il 2026-07-29**, su decisione di Simone: la Fase 9 **raccoglie** le statistiche nel database e basta — nessuna interfaccia. Questa fase decide **come rappresentarle**. Il documento serve prima di tutto da catalogo: elenca tutto ciò che avremo a disposizione, così la fase si costruisce su un inventario e non sulla memoria.

## Obiettivo

Dare una forma leggibile ai numeri che la Fase 9 comincia a raccogliere: quali si mostrano, a chi, dove, con che aggregazione, e quali invece restano solo dati che non meritano una pagina.

## Perché è una fase a sé

Raccogliere e rappresentare sono due lavori diversi con rischi diversi. La raccolta è vincolata: le colonne devono nascere **tutte insieme** nel reset di schema della Fase 9, perché `create_all` non altera le tabelle esistenti e ogni ripensamento costa un'altra ricreazione del database. La rappresentazione invece non ha vincoli di quel tipo e può essere decisa con calma, guardando numeri veri già accumulati per qualche settimana — che è il modo giusto di scegliere un grafico, invece di immaginarselo su una tabella vuota.

## Risultato apprezzabile

Da definire in fase. Le due direzioni sulle quali decidere: una pagina di dettaglio per prodotto (accanto al grafico dei prezzi) e una pagina di salute per scraper nell'area admin.

---

## Inventario — cosa avremo a disposizione

### A. Quello che il sistema già registra oggi (da non re-inventare)

| Dove | Cosa | Note |
|---|---|---|
| `scrape_run` | una riga per run: `trigger`, `slot`, `started_at`, `finished_at`, `status`, `users_processed`, `products_found`, `products_new`, `price_changes`, `products_removed`, `products_excluded`, `http_requests`, `cache_hits`, `error_message` | **ha retention**: le righe vengono potate, quindi i totali storici non si possono ricavare da qui per sempre |
| `scrape_user_log` | lo stesso dettaglio **per utente** dentro una run | **ha retention** |
| `price_history` | append-only, una riga a ogni cambio di prezzo **o** disponibilità, con `is_available` | **nessuna retention**: è la serie storica completa, ed è la base dei grafici di fase 8 |
| `products` | `first_seen_at`, `last_seen_at` (l'ora della risposta vera, non del nostro orologio — `9.X4`), `removed` | `first_seen_at` dà gratis "in catalogo da N giorni" |
| `system_log` | eventi per sorgente (`worker`, `scraper`, `web`, `notifier`, `alert`) | testo, non numeri: utile a spiegare un'anomalia, non a misurarla |
| cooldown scrape-now | ancora dell'ultimo scrape manuale per `(scraper, utente)` | — |

> Conseguenza da tenere presente per tutta la fase: **le uniche memorie durevoli sono `price_history` e i contatori cumulativi che la Fase 9 introduce.** Tutto ciò che sta in `scrape_run` è una finestra recente.

### B. Per prodotto — raccolte da `9.B6b` (Fase 9)

Sulla riga di catalogo, quindi **per utente** (due utenti che seguono lo stesso prodotto hanno contatori distinti).

| Colonna | Significato preciso | Trappola da ricordare |
|---|---|---|
| `observations` | quante volte il prodotto è stato **letto dal sito** | conta **solo le letture fresche**: una consegna servita dalla cache non incrementa, altrimenti misurerebbe "quante volte l'abbiamo riprocessato" |
| `cache_hits` | quante volte è stato consegnato da una pagina **in cache** | per i prodotti di categoria una sola cache hit HTTP serve fino a 50 prodotti: significa "il mio dato veniva da una pagina in cache", non "una richiesta risparmiata per me" |
| `price_changes` | quante volte è cambiato **il prezzo** | distinto dalla disponibilità: il contatore omonimo di `scrape_run` incrementa anche sui cambi di disponibilità e sulla prima riga di storia — conta "righe di storia scritte" |
| `availability_changes` | quante volte è cambiata **la disponibilità** | separa "il prezzo balla" da "va sempre esaurito" |
| `price_min` / `price_min_at` | minimo osservato e quando | è il **minimo storico** che la [fase 11](phase-11-insights.md) vuole come badge |
| `price_max` / `price_max_at` | massimo osservato e quando | dà l'intervallo: "39,99, tra 24,90 e 44,00" dice più del solo minimo |
| `last_price_change_at` | da quanto il prezzo corrente è fermo | compagno del `Last seen` di `9.X3`: una linea piatta si legge diversamente se dura tre giorni o otto mesi |
| `removed_at` | quando è stato delistato | oggi la spazzata alza `removed` senza registrare quando; serve anche alla [fase 15](phase-15-catalog-notifications.md) |

**Metriche derivate interessanti** (da calcolare, non da salvare): volatilità = `price_changes / observations`; resa della cache = `cache_hits / (observations + cache_hits)`; convenienza attuale = distanza dal `price_min`; età del dato = adesso − `last_seen_at`.

### C. Per scraper — raccolte da `9.B6c` (Fase 9)

Una riga per `plugin_id`, **globale** (non per utente), cumulativa e non potata: è la memoria lunga che `scrape_run` non può essere.

| Gruppo | Contatori | A cosa risponde |
|---|---|---|
| **Attività** | `runs_total`, `runs_ok`, `runs_failed`, `runs_skipped_locked`, `last_run_at`, `last_success_at`, `last_failure_at`, `consecutive_failures` | quante volte ha girato, da quando non gira bene, e se sta fallendo *adesso* o ha fallito una volta a marzo |
| **Traffico** | `http_requests_total`, `cache_hits_total`, `bytes_downloaded_total`, `politeness_wait_s_total`, `run_seconds_total` | quanto pesiamo sul sito, quanto ci fa risparmiare la cache, e **quanta parte di una run è pura attesa di cortesia** — il numero che dice se il `Crawl-delay` è il vero costo |
| **Salute verso il sito** | `rate_limited_total` (429), `gate_hits_total`, `gate_cleared_total`, `robots_denied_total` | oggi **non è contato da nessuna parte**: esiste solo come righe di log. È esattamente ciò che è mancato durante il blocco del 25 luglio, quando la domanda era "da quando succede e quanto spesso" |
| **Resa** | `products_delivered_total`, `pages_fetched_total`, `parse_failures_total` | quanto rende una richiesta, e se il parser sta silenziosamente perdendo pezzi |

**Metriche derivate interessanti**: prodotti per richiesta (`products_delivered_total / http_requests_total`), tasso di successo (`runs_ok / runs_total`), quota di attesa (`politeness_wait_s_total / run_seconds_total`), tasso di cache (`cache_hits_total / (http_requests_total + cache_hits_total)`).

---

## Da decidere in questa fase

- **Dove vivono.** Il prodotto ha già una pagina naturale (Storico prezzi, accanto al `Last seen`); lo scraper ha già `/admin/scrapers`. Ma "una tabella di numeri" non è una risposta: va deciso quali numeri meritano di essere visti e quali sono solo diagnostica.
- **Numeri o grafici.** Contatori cumulativi non hanno un andamento nel tempo; `price_history` sì. Un grafico su un contatore cumulativo è una retta e non dice nulla: se si vuole un andamento (richieste al giorno, cache al giorno) servono **serie temporali**, cioè `scrape_run` — che però ha retention. Da decidere se aggregare per giorno prima della potatura.
- **Azzeramento.** Un contatore cumulativo che non si azzera mai è ingannevole dopo un cambio di configurazione (esempio vero: la cortesia passata da 1,5s a 11s in `0.8.1` — i totali prima e dopo non sono confrontabili). Serve almeno un `since` dichiarato, o un reset esplicito dall'admin.
- **Chi vede cosa.** Le statistiche per prodotto sono dell'utente; quelle per scraper sono dell'amministratore. Il `super-user` di `9.B8` è un caso da decidere.
- **Export.** La [fase 11](phase-11-insights.md) prevede già l'export dei dati: va deciso se queste statistiche ci rientrano o restano solo da guardare.
- **Retention e aggregazione**: se e come conservare una serie giornaliera prima che `scrape_run` venga potato.

## Definition of Done

- [ ] Deciso, per ogni statistica dell'inventario, se si mostra e dove — **anche quando la decisione è "non si mostra"**.
- [ ] Nessun numero in pagina senza la sua definizione: i contatori qui sopra hanno tutti una trappola di lettura, e un numero senza didascalia si interpreta a caso.
- [ ] [docs](../../docs/) aggiornata in inglese con la sola parte implementata (DOC-12).

## Riferimenti

[Fase 9 — Dragon Store completo](phase-09-dragonstore-complete.md) · [Fase 11 — Summary, analisi prezzi, export](phase-11-insights.md) · [Fase 15 — Notifiche sul catalogo](phase-15-catalog-notifications.md) · [schema del database](../../docs/4-capabilities/database/schema.md)
