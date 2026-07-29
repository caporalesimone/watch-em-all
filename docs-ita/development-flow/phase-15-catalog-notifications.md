# Fase 15 — Notifiche sul catalogo (novità e sparizioni)

> Stato: 💡 idea / da dettagliare · **post-1.0** (oltre il perimetro della [1.0](../1-business/product-overview.md)) · Prerequisiti: Fase 7 (notifiche), Fase 9 (categorie e `9.B9`) · [Indice del flusso](README.md)
>
> **Annotata il 2026-07-29**, durante l'analisi della Fase 9, su domanda di Simone: *"se l'utente volesse essere informato di prodotti nuovi a catalogo o rimossi, come potrebbe farlo?"*. Gli MVP qui sotto sono abbozzati e vanno dettagliati (analisi → proposta → ok) prima di diventare lavoro reale.

## Obiettivo

Oggi l'utente è avvisato **solo a livello di carrello**: il motore degli alert diffa i carrelli e il digest è organizzato per carrello. Il **catalogo** non parla. Questa fase introduce una seconda classe di eventi, di livello catalogo — *è entrato un prodotto nuovo*, *un prodotto è sparito dal sito* — instradata negli stessi canali già esistenti.

## Perché dopo la Fase 9 e non prima

Finché il catalogo cresce solo quando è l'utente ad aggiungere un URL, "nuovo prodotto a catalogo" è una notizia che l'utente si dà da solo. È la **categoria** a cambiarne la natura: da fase 9 il catalogo si popola da sé a ogni run, e *"nella categoria che segui è uscito un titolo nuovo"* diventa l'informazione di maggior valore che il sistema possa dare — in pratica una notifica di novità in negozio. Prima delle categorie questa fase non avrebbe avuto un caso d'uso reale.

## Risultato apprezzabile

Segui la categoria "Il Richiamo di Cthulhu". Esce un manuale nuovo: la mattina dopo lo sai, senza aver chiesto niente. Un prodotto sparisce dal sito: lo sai una volta sola, quando succede.

## Il punto architetturale

**Il segnale esiste già e viene scartato.** Ogni consegna passa da `update_catalog`, che calcola il delta e restituisce `DeltaCounters` — nuovi, cambi di prezzo, rimossi (CATSVC-R6). Oggi quei numeri finiscono **aggregati** nella riga di `scrape_run` e nessuno li conserva per prodotto. Non serve un rilevatore nuovo: serve conservare e instradare un evento che già produciamo.

**Il costo vero è che il motore degli alert è per carrello.** La baseline sta in `alert_snapshot` con chiave `(utente, carrello)` e il digest è organizzato per carrello; un evento di catalogo non ha un carrello a cui appendersi. Serve quindi una **seconda sorgente di eventi**, di livello catalogo, che confluisce nello stesso digest e negli stessi notificatori — il livello canale si riusa integralmente, il punto d'innesto è il digest.

## MVP (abbozzati)

### Backend

- [ ] **15.B1 — Eventi di catalogo persistiti** (~1h): il delta per prodotto (`entrato` / `sparito`) smette di essere solo un contatore e diventa un evento leggibile. Serve un `products.removed_at` (la spazzata oggi alza `removed` ma non registra *quando*); i "nuovi" sono già gratis con `first_seen_at`. **Vale la regola: una colonna nuova non si aggiunge da sola** — va agganciata a un'altra modifica di schema. *Verifica: due run consecutive → gli eventi corrispondono al delta dichiarato.*
- [ ] **15.B2 — Sottoscrizione per watch di categoria** (~1h): interruttore sulla riga della categoria, accanto a "includi ammaccati", **spento** di default. Una categoria *è* già una ricerca permanente: è il posto naturale dove chiedere "dimmi cosa entra ed esce da questa". Un interruttore globale di profilo resta il caso degenere, eventualmente dopo. *Verifica: toggle spento → nessun evento.*
- [ ] **15.B3 — Semina silenziosa alla prima consegna** (~30m): aggiungere una categoria da 100 prodotti li rende tutti "nuovi", e una notifica da 100 righe è spam. La prima osservazione **semina in silenzio** e si notifica solo dalle successive — è la regola che il motore degli alert applica già ai membri di un carrello, si riusa. *Verifica: categoria appena aggiunta → zero notifiche; prodotto che compare alla run dopo → una notifica.*
- [ ] **15.B4 — Una volta sola, e precedenza sugli eventi di carrello** (~1h): l'evento si emette **alla transizione**, non a ogni run finché lo stato dura (stessa forma di `PRODUCT_DELISTED` in `9.B9`). E va decisa la **precedenza**: un prodotto che sta in un carrello *e* in una categoria seguita genererebbe due messaggi — proposta, l'evento di carrello vince e il digest di catalogo elenca il resto. *Verifica: prodotto in carrello e in categoria → un solo messaggio.*
- [ ] **15.B5 — Tetto al volume** (~30m): una categoria da mille prodotti può muoversi parecchio. Il digest dichiara il totale e ne mostra un numero limitato ("12 nuovi, i primi 5 qui sotto"), senza troncare in silenzio. *Verifica: 30 novità → totale corretto e nessuna omissione taciuta.*

### Frontend

- [ ] **15.F1 — Interruttore sulla riga della categoria** (~30m): stessa forma degli altri toggle del plugin. *Verifica: stato riflesso dopo un reload.*
- [ ] **15.F2 — Resa nel digest e nella cronologia in-app** (~1h): una sezione "Catalogo" accanto a quelle dei carrelli, con i prodotti entrati e usciti raggruppati per categoria. *Verifica: mail e cronologia in-app dicono la stessa cosa.*

## Da decidere prima di iniziare

- **Granularità**: per watch di categoria (proposta), globale per utente, o per scraper.
- **Anche i prodotti singoli?** Un watch di prodotto non può generare "nuovo" (l'ha aggiunto l'utente), ma può generare "sparito" — che però è già coperto da `9.B9` se il prodotto sta in un carrello, e non lo è se non ci sta.
- **Il ricomparire**: `9.B9` lascia aperta la stessa domanda per i carrelli; le due risposte devono coincidere.
- **`removed_at`** va agganciato alla prossima modifica di schema, non fatto da solo.

## Definition of Done

- [ ] Un prodotto che entra in una categoria seguita produce **una** notifica, alla run in cui entra.
- [ ] Un prodotto che sparisce ne produce **una**, alla transizione.
- [ ] Una categoria appena aggiunta non produce nulla.
- [ ] Nessun doppio avviso per un prodotto che sta anche in un carrello.
- [ ] [docs](../../docs/) aggiornata in inglese con la sola parte implementata (DOC-12).

## Riferimenti

[Fase 9 — Dragon Store completo](phase-09-dragonstore-complete.md) · [Fase 7 — Notifiche Email](phase-07-email-notifier.md) · [alert engine](../../docs/4-capabilities/core/alert-engine.md) · [catalog update service](../../docs/4-capabilities/core/catalog-update-service.md)
