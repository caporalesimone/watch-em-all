# Fase 10b — Statistiche per prodotto

> Stato: 💡 da dettagliare · Prerequisiti: Fase 10 (che mostra la metà admin e fissa le convenzioni di lettura) · [Indice del flusso](README.md)
>
> **Annotata il 2026-07-29** come "Fase 9b — Statistics", su decisione di Simone: la Fase 9 **raccoglie** le statistiche nel database e basta — nessuna interfaccia. **Ristretta e rinumerata il 2026-08-02**: la metà **per scraper** è stata assorbita dalla [Fase 10](phase-10-admin-governance.md) (`10.B20`, `10.B21`, `10.F15`), perché è una pagina admin e quella fase la stava già costruendo in `10.B6`/`10.F5`. Qui resta la metà **per prodotto**, che è una pagina **utente** e non cade nella Definition of Done della fase 10. Il numero dice la posizione, non l'ordine di stesura: viene dopo la 10, prima della 11.

## Obiettivo

Dare una forma leggibile ai numeri che la Fase 9 raccoglie **su ogni riga di catalogo**: quali si mostrano all'utente, dove, con che aggregazione, e quali invece restano dati che non meritano una pagina.

## Perché è una fase a sé, e perché sta qui

Raccogliere e rappresentare sono due lavori diversi con rischi diversi. La raccolta era vincolata: le colonne dovevano nascere **tutte insieme** nel reset di schema della Fase 9 (`9.X6a`), perché `create_all` non altera le tabelle esistenti e ogni ripensamento costa un'altra ricreazione del database. La rappresentazione non ha vincoli di quel tipo, e ha invece un requisito che solo il tempo soddisfa: **numeri veri già accumulati**. Il database è stato ricreato il 2026-07-29, quindi ogni contatore riparte da lì; scegliere un grafico su tre giorni di dati significa immaginarselo.

Sta **dopo la 10** anche per una seconda ragione, non solo per l'attesa: è la fase 10 a fissare le convenzioni di lettura di questi numeri — didascalia obbligatoria, `since` dichiarato, cumulativi in cifre e non in grafico — e lo fa su una pagina admin, dove sbagliare costa poco. Quelle convenzioni si ereditano qui, dove il lettore è l'utente.

## Risultato apprezzabile

Da definire in fase. La direzione: un pannello di dettaglio per prodotto, accanto al grafico dei prezzi della [Fase 8](phase-08-price-charts.md) e al `Last seen` di `9.X3` — che è già il posto dove l'utente si chiede *quanto mi fido di questo numero*.

---

## Inventario — cosa abbiamo già nel database

### A. Quello che il sistema registrava da prima (da non re-inventare)

| Dove | Cosa | Note |
|---|---|---|
| `price_history` | append-only, una riga a ogni cambio di prezzo **o** disponibilità, con `is_available` | **nessuna retention**: è la serie storica completa, ed è la base dei grafici di fase 8 |
| `products` | `first_seen_at`, `last_seen_at` (l'ora della risposta vera, non del nostro orologio — `9.X4`), `removed` | `first_seen_at` dà gratis "in catalogo da N giorni" |
| `scrape_run` / `scrape_user_log` | contatori per run, e lo stesso dettaglio per utente dentro la run | **hanno retention** (potati oltre `log_retention_days`): sono una finestra recente, non una memoria. Li rappresenta la [Fase 10](phase-10-admin-governance.md) |
| `system_log` | eventi per sorgente (`worker`, `scraper`, `web`, `notifier`, `alert`) | testo, non numeri: utile a spiegare un'anomalia, non a misurarla |

### B. Per prodotto — raccolte da `9.B6b`, mai mostrate

Stanno sulla riga di catalogo, quindi sono **per utente**: due utenti che seguono lo stesso prodotto hanno contatori distinti. Le scrive [`catalog.py`](../../src/core/catalog.py).

| Colonna | Significato preciso | Trappola da ricordare |
|---|---|---|
| `observations` | quante volte il prodotto è stato **letto dal sito** | conta **solo le letture fresche**: una consegna servita dalla cache non incrementa, altrimenti misurerebbe "quante volte l'abbiamo riprocessato" |
| `cache_hits` | quante volte è stato consegnato da una pagina **in cache** | per i prodotti di categoria una sola cache hit HTTP serve fino a 50 prodotti: significa "il mio dato veniva da una pagina in cache", non "una richiesta risparmiata per me" |
| `price_changes` | quante volte è cambiato **il prezzo** | distinto dalla disponibilità: il contatore omonimo di `scrape_run` incrementa anche sui cambi di disponibilità e sulla prima riga di storia — conta "righe di storia scritte" |
| `availability_changes` | quante volte è cambiata **la disponibilità** | separa "il prezzo balla" da "va sempre esaurito" |
| `price_min` / `price_min_at` | minimo osservato e quando | è il **minimo storico** che la [fase 11](phase-11-insights.md) vuole come badge — vedi il conflitto qui sotto |
| `price_max` / `price_max_at` | massimo osservato e quando | dà l'intervallo: "39,99, tra 24,90 e 44,00" dice più del solo minimo |
| `last_price_change_at` | da quanto il prezzo corrente è fermo | compagno del `Last seen` di `9.X3`: una linea piatta si legge diversamente se dura tre giorni o otto mesi |
| `removed_at` | quando è stato delistato | serve alle pulizie di `9.B7` (ordinare per "da quanto") e alla [fase 15](phase-15-catalog-notifications.md) |

**Metriche derivate interessanti** (da calcolare, non da salvare): volatilità = `price_changes / observations`; resa della cache = `cache_hits / (observations + cache_hits)`; convenienza attuale = distanza dal `price_min`; età del dato = adesso − `last_seen_at`.

---

## Da decidere in questa fase

- **⚠ Il conflitto con la Fase 11, che è la decisione più importante.** La [fase 11](phase-11-insights.md) prevede `11.B3` (`product_stats` con medie pesate sul tempo), `11.B4` (`GET /api/products/{id}/stats` e il flag `is_all_time_low`) e `11.F2`/`11.F3` (pannello statistiche accanto al grafico, badge minimo storico) — **calcolati da `price_history`**. Ma `price_min` esiste già come colonna, aggiornata a ogni osservazione. Sono due strade per la stessa domanda, e se atterrano entrambe l'utente vede due minimi storici che possono non coincidere: è lo stesso difetto dichiarato in `9.F8` (la regola della differenza scritta in Python e in TypeScript). **Da chiudere prima di scrivere una riga**: o questa fase assorbe `11.B4`/`11.F2`/`11.F3`, o rinuncia al minimo storico e lascia tutto alla 11. Mai entrambe.
- **Dove vive il pannello.** Lo Storico prezzi ha già il grafico e il `Last seen`, ed è la pagina dove queste domande nascono. Ma "una tabella di numeri" non è una risposta: va deciso quali meritano di essere visti e quali sono solo diagnostica.
- **Numeri o grafici.** Vale la regola fissata in `10.F15`: un contatore cumulativo graficato è una retta e non dice nulla. L'andamento nel tempo ce l'ha `price_history`, che il grafico di fase 8 già disegna.
- **Chi vede cosa.** Queste statistiche sono dell'utente, e per costruzione sono già per-utente. Il `super-user` di `9.B8` è un caso da decidere.
- **Export.** La [fase 11](phase-11-insights.md) prevede l'export dei dati dell'utente (`11.B7`/`11.B8`): va deciso se queste colonne ci rientrano o restano solo da guardare.

## Definition of Done

- [ ] Deciso, per ogni statistica dell'inventario B, se si mostra e dove — **anche quando la decisione è "non si mostra"**.
- [ ] Nessun numero in pagina senza la sua definizione: i contatori qui sopra hanno tutti una trappola di lettura, e un numero senza didascalia si interpreta a caso.
- [ ] Il minimo storico ha **una sola** implementazione in tutto il prodotto, e si sa quale.
- [ ] [docs](../../docs/) aggiornata in inglese con la sola parte implementata (DOC-12).

## Riferimenti

[Fase 9 — Dragon Store completo](phase-09-dragonstore-complete.md) · [Fase 10 — Governo admin](phase-10-admin-governance.md) (la metà per scraper) · [Fase 11 — Summary, analisi prezzi, export](phase-11-insights.md) · [schema del database](../../docs/4-capabilities/database/schema.md)
