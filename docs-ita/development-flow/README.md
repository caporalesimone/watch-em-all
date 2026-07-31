# Development Flow — Indice e stato di avanzamento

> Come si sviluppa Watch 'Em All: **per piccoli MVP apprezzabili**. Ogni MVP si risolve in **al massimo un'ora** di sviluppo; ogni **fase** si chiude con qualcosa di **utilizzabile e dimostrabile** — mai "lavoro a metà" che vive solo nei branch.

## Le regole del flusso

1. **Un MVP = una PR**: piccolo, completo, mergiato su `main` verde ([regole di processo](../../docs/developer-rules/README.md)).
2. **Ordine delle fasi vincolante, ordine degli MVP interno flessibile** (salvo dipendenze indicate).
3. **Una fase è chiusa solo se la sua *Definition of Done* è vera** provandola da utente, non leggendo il codice.
4. **Le checkbox si aggiornano nella stessa PR** che completa l'MVP (questo indice + il documento di fase).
5. Se durante una fase emerge lavoro non previsto: o è un MVP nuovo nella fase giusta, o un [future improvement](../future-improvements/README.md). Mai scope-creep silenzioso.
6. **Un MVP = al massimo un'ora** di sviluppo concentrato: se in fase di analisi (o a metà lavoro) si capisce che non ci sta, **si spezza prima di iniziare** — un MVP più lungo di un'ora era due MVP.
7. **I mock sono ammessi** per chiudere un MVP nell'ora — purché **dichiarati**: il documento di fase (e la PR) dicono esplicitamente *cosa* è mockato e *quale MVP* lo sostituirà. Mai mock silenziosi.
8. In ogni fase gli MVP sono separati in **Backend** (`N.B*`), **Frontend** (`N.F*`) ed eventuali **Trasversali** (`N.T*`). Gli MVP frontend dipendono dagli endpoint dei corrispondenti backend, ma possono partire in parallelo sviluppando contro il contratto documentato in [api/endpoints.md](../api/endpoints.md) (l'API nasce nel catalogo prima dell'implementazione).
9. **Docs inglesi a fine fase** (DOC-12): la chiusura di una fase include l'aggiornamento della documentazione inglese in `docs/` (root del repo, la wiki canonica designata) con l'equivalente della documentazione della **sola parte implementata**, stessa alberatura di `docs-ita/`. È un item della Definition of Done di ogni fase.

## Avanzamento

- [x] **Fase 0 — Pipeline e processo** → [phase-00-pipeline.md](phase-00-pipeline.md)
  *Risultato: container (stub), workflow GitHub, immagine dev sul branch, release sul tag: il processo è rodato end-to-end prima di qualsiasi codice di prodotto. Chiusa, rodata su `0.0.16`.*
- [x] **Fase 1 — Fondamenta** → [phase-01-foundations.md](phase-01-foundations.md) — rilasciata `0.1.0`
  *Risultato: l'app parte con Docker, si fa login, la shell c'è.*
- [x] **Fase 2 — Plugin system** → [phase-02-plugin-system.md](phase-02-plugin-system.md) — rilasciata `0.2.0`
  *Risultato: un plugin demo appare da solo in sidebar con la sua pagina.*
- [x] **Fase 3 — Catalogo e primo scrape** → [phase-03-catalog-first-scrape.md](phase-03-catalog-first-scrape.md) — rilasciata `0.3.4`
  *Risultato: prodotti reali di Dragon Store nel Product Picker, catalogo con delta e storico, scrape lanciato a mano. La **gestione utenti** (crea/elenca + shell sdoppiato per ruolo) è stata anticipata dalla Fase 10 perché serve un account `user` per provare il resto — i ruoli non si sovrappongono (l'admin governa, non possiede carrelli); in Fase 10 restano reset/disabilita/cancellazione differita/filtri/notifiche.*
- [x] **Fase 4 — Worker e scheduling** → [phase-04-worker-scheduling.md](phase-04-worker-scheduling.md) — rilasciata `0.4.0`
  *Risultato: lo scraping parte da solo agli orari decisi; l'admin lo osserva nei log.*
- [x] **Fase 5 — Carrelli** → [phase-05-carts.md](phase-05-carts.md) — rilasciata `0.5.0`
  *Risultato: carrelli con totali, adjustments, soglia e provenienza.*
- [x] **Fase 6 — Alert in-app** → [phase-06-alerts-in-app.md](phase-06-alerts-in-app.md) — rilasciata `0.6.0`
  *Risultato: cambio prezzo → notifica nello Storico alert appena lo scrape aggiorna i prezzi (event-driven).*
- [x] **Fase 7 — Notifiche Email** 🎉 → [phase-07-email-notifier.md](phase-07-email-notifier.md) — rilasciata `0.7.0`
  *Risultato: **la mail col digest arriva in casella — il prodotto fa il suo mestiere (0.1)**.*
- [x] **Fase 8 — Grafici dello storico** 📈 → [phase-08-price-charts.md](phase-08-price-charts.md) — completata (`0.8.0`)
  *Risultato: grafici interattivi per prodotto e carrello.*
- [ ] **Fase 9 — Dragon Store completo** → [phase-09-dragonstore-complete.md](phase-09-dragonstore-complete.md) — *implementata (`0.9.0`), in attesa della validazione manuale*
  *Risultato: monitoraggio per categorie, catalogo gestibile.*
- [ ] **Fase 9b — Statistics** → [phase-09b-statistics.md](phase-09b-statistics.md)
  *Risultato: le statistiche che la Fase 9 raccoglie nel database (per prodotto e per scraper) trovano una rappresentazione. La Fase 9 non ne mostra nessuna: si decide qui, guardando numeri veri già accumulati invece di immaginarseli su una tabella vuota.*
- [ ] **Fase 10 — Governo admin** → [phase-10-admin-governance.md](phase-10-admin-governance.md)
  *Risultato: plancia admin completa — statistiche, limiti, utenti, manutenzione. (Creazione/elenco utenti **anticipati** come MVP prima della Fase 3; qui restano reset password, disabilita/riabilita, cancellazione differita + restore, filtri di stato, ultimo accesso, notifiche di cortesia, dashboard del carico.)*
- [ ] **Fase 11 — Summary, analisi prezzi, export** → [phase-11-insights.md](phase-11-insights.md)
  *Risultato: report periodico, badge minimo storico e convenienza, export dei dati.*
- [ ] **Fase 12 — Rifinitura e 1.0** → [phase-12-polish-v1.md](phase-12-polish-v1.md)
  *Risultato: secondo canale (Discord), audit i18n English-first, CI piena: release 1.0.*
- 💡 **Fase 13 — Resilienza dello scraping** (post-1.0, idea da dettagliare) → [phase-13-scraping-resilience.md](phase-13-scraping-resilience.md)
  *Risultato: le connessioni verso i siti usano user-agent (e opzioni di richiesta) decisi dal core, con eventuale preferenza per-scraper. Annotazione, oltre il perimetro 1.0.*
- 💡 **Fase 14 — Sito usabile da mobile** (post-1.0, idea da dettagliare) → [phase-14-mobile.md](phase-14-mobile.md)
  *Risultato: le pagine utente si usano da telefono senza zoom né scorrimento orizzontale (14.1); il perimetro dell'area admin (14.2) è da discutere prima, perché è la parte cara.*
- 💡 **Fase 15 — Notifiche sul catalogo** (post-1.0, idea da dettagliare) → [phase-15-catalog-notifications.md](phase-15-catalog-notifications.md)
  *Risultato: sai quando un prodotto entra o sparisce dalle categorie che segui, non solo quando si muove un carrello. Ha senso solo dopo le categorie della Fase 9: è da lì che il catalogo cresce da solo.*
- 💡 **Fase 16 — Custodia dello storico prezzi** (post-1.0, idea da dettagliare) → [phase-16-history-custody.md](phase-16-history-custody.md)
  *Risultato: l'admin può guardare e potare lo storico prezzi, la sola tabella che per scelta non si cancella mai da sé. Nasce dalla Fase 9, che ha reso lo storico proprietà del prodotto e non dell'utente: da lì esistono catene che nessuno referenzia più, e decidere il loro destino è governo, non pulizia.*

## La logica dell'ordine

```mermaid
flowchart LR
    F0[0 Pipeline] --> F1[1 Fondamenta] --> F2[2 Plugin system] --> F3[3 Primo scrape] --> F4[4 Worker]
    F4 --> F5[5 Carrelli] --> F6[6 Alert in-app] --> F7[7 Email 🎉 0.1]
    F7 --> F8[8 Grafici] --> F9[9 DragonStore full] --> F10[10 Admin] --> F11[11 Insight] --> F12[12 1.0]
    F12 -.post-1.0.-> F13[13 Resilienza scraping 💡]
```

- La fase 0 costruisce e **roda il processo** (CI, immagini dev sul branch, release sul tag, deploy kit) con container stub: **prima che esista il prodotto, esiste il suo flusso di rilascio** — ogni fase successiva ne beneficia dalla prima PR.
- Le fasi 1-7 percorrono la **catena del valore minima** del prodotto (login → plugin → dati → automazione → carrelli → alert → consegna): alla fase 7 il sistema fa già, per intero, il suo mestiere su prodotti singoli.
- Le fasi 8-11 **arricchiscono** (grafici, categorie, governo, insight) su un prodotto che già si usa tutti i giorni — ogni fase è valore visibile, non infrastruttura.
- La fase 12 chiude il perimetro della [1.0](../1-business/product-overview.md).
- Dalla **fase 13** in poi sono **enhancement post-1.0** (idee annotate, da dettagliare): non fanno parte del perimetro 1.0 e si promuovono quando diventano attuali — affini ai [future improvements](../future-improvements/README.md), ma tenute qui perché sono fasi di lavoro vere e proprie quando partiranno.
