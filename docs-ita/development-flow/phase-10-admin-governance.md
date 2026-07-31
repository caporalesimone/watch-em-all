# Fase 10 — Governo admin

> Stato: 🚧 in corso (avviata 2026-08-01) · Prerequisiti: Fase 4 (Fase 9 consigliata: più dati da osservare) · [Indice del flusso](README.md)

## Obiettivo

Completare la plancia dell'admin: statistiche e drill-down delle run, limiti di sistema modificabili a caldo, gestione utenti completa (con cancellazione differita), dashboard di sistema, messaggi agli utenti, manutenzione (retention e purge).

## Risultato apprezzabile

L'admin apre il monitoraggio e capisce in un colpo d'occhio quanto lavorano gli scraper (durate, richieste, trend), vede la giornata pianificata nella vista calendario, scende nel dettaglio per-utente di una run lenta, regola timeout e retention dalla UI, crea e gestisce gli account.

## MVP

### Catalogo (rifinitura, chiesta il 2026-07-31)

> Non è governo admin: è una rifinitura di una pagina **utente** che Simone ha chiesto di fare all'inizio di questa fase. Sta qui per scelta di sequenza, non perché appartenga al tema.

- [ ] **10.F0 — La colonna Source mostra l'icona, non il nome** (~30m): nella tabella del catalogo la provenienza occupa oggi una colonna di testo — icona **più** nome dello scraper ripetuti su ogni riga, per un'informazione che in un'installazione con un solo negozio è costante e in una con tre si riconosce a colpo d'occhio dal logo. **È l'icona a portare il riconoscimento**, e per questo va ingrandita fino alla dimensione del riquadro dell'anteprima prodotto: le due celle si allineano, e un logo a 16px non identifica niente — togliere il nome *e* lasciare l'icona piccola renderebbe la colonna meno leggibile di adesso, non più. Il **tooltip** col nome al passaggio del mouse è un aiuto in più, non il canale dell'informazione (decisione di Simone, 2026-07-31). Due vincoli di implementazione: `SourceTag` è condiviso (catalogo, dettaglio carrello, pagine degli scraper), quindi la variante "sola icona" va aggiunta come **opzione del componente**, non copiata, o le tre pagine divergeranno alla prima modifica; e l'`alt` dell'immagine porta comunque il nome dello scraper — non per ridondanza col tooltip, ma perché un'icona con `alt` vuoto per uno screen reader **non esiste**, e quella cella resterebbe muta invece di ridondante. Costa un attributo. *Verifica: la colonna mostra solo il logo alla stessa altezza dell'anteprima, l'hover ne dice il nome, uno screen reader legge il nome dello scraper, e le altre pagine che usano `SourceTag` non cambiano aspetto.*

### Backend

- [ ] **10.B1 — Utenti: create/reset/disable** (~1h): API con invalidazione token (`token_version`), login a credenziali corrette su disabilitato → codice `account_disabled` (AUTH-R10) ([user-management](../3-features/admin/user-management.md)). *Verifica: utente disabilitato → fuori entro la scadenza dell'access token.*
- [ ] **10.B2 — Ultimo accesso + lista filtrabile** (~1h): `last_login_at` aggiornato al login, lista ordinabile per ultimo accesso (USR-R13), filtro `?status=` attivo/disabilitato/in-cancellazione (USR-R14). *Verifica: ordinamento individua gli inattivi; filtro corretto.*
- [ ] **10.B3 — Cancellazione soft con scadenza** (~1h): delete = disattiva + `deletion_marked_at` + `deletion_due_at` + notifica di cortesia; restore = annulla → **disabilitato** (mai attivo). *Verifica: delete non elimina alcun dato e fissa la scadenza; annullo → disabilitato.*
- [ ] **10.B4 — Hook `delete_user_data` nei plugin** (~1h): metodo su BasePlugin (default no-op) + implementazione nei plugin con tabelle proprie. *Verifica: chiamata sul demo/Dragon Store → righe utente del plugin sparite.*
- [ ] **10.B5 — Purge automatico utenti** (~1h): job giornaliero del worker (CRON-R10) per gli account con `deletion_due_at` scaduta: plugin in sequenza, cascata core solo se tutti ok, fallimento → utente resta marcato + errore in system_log, retry il giorno dopo (USR-R9/R10). *Verifica: account scaduto → eliminato senza righe residue; plugin che fallisce → dati intatti e nuovo tentativo.*
- [ ] **10.B6 — API run e statistiche** (~1h): elenco run paginato, dettaglio per-utente, `GET /api/admin/scrapers/{id}/stats` (serie per i trend). *Verifica: dati coerenti con le run accumulate.*
- [ ] **10.B7 — Impostazioni di sistema** (~1h): `system_settings` con seed dei default (incluso `user_deletion_retention_days`), effetto a caldo (timeout, soglia recuperi, periodo di grazia pro-futuro). *Verifica: timeout ridotto a caldo → la run lunga successiva è terminata; grazia cambiata → vale solo per le nuove marcature.*
- [ ] **10.B8 — Retention + purge alert** (~1h): retention automatica di log e run nella manutenzione giornaliera ([system-logs-and-maintenance](../../docs/3-features/admin/system-logs-and-maintenance.md)); `DELETE /api/admin/alerts?before=`. *Verifica: vecchi oltre retention spariti; notifiche recenti intatte.*
- [ ] **10.B9 — Dashboard: aggregati globali** (~1h): `GET /api/admin/dashboard` — totali di sistema, statistiche notifiche ([admin-dashboard](../3-features/admin/admin-dashboard.md)). *Verifica: i totali tornano con i dati delle tabelle.*
- [ ] **10.B10 — Dashboard: ranking utenti** (~1h): `/dashboard/users` — ranking per utente e per (utente, scraper), `http_requests` per-utente da `scrape_user_log`. *Verifica: nessun contenuto utente nelle risposte (DASH-R6).*
- [ ] **10.B11 — Interruttore globale notifier** (~1h): colonna `enabled` su `notifier_admin_config`, `PATCH /api/admin/notifiers/{id}`; canale off = non disponibile per tutti, config utente preservate (PCFG-R8). *Verifica: disabilitato → consegne saltate per tutti; riattivato → tornano senza riconfigurare.*
- [ ] **10.B12 — Messaggi admin: invio** (~1h): tabella `admin_message`, kind `admin_message`/`system_message` su `alert_log`, `POST /api/admin/messages` a tutti/un utente sulla pipeline notifiche esistente ([admin-notifications](../3-features/admin/admin-notifications.md)). *Verifica: utente senza canali riceve il messaggio in-app (ADMSG-R2).*
- [ ] **10.B13 — Messaggi admin: esiti** (~1h): `GET /api/admin/messages` con esiti per destinatario/canale. *Verifica: l'admin non vede lo stato letto/non letto (ADMSG-R5).*
- [ ] **10.B14 — Helper Markdown nel contesto** (~1h): `markdown.to_html()` (markdown-it-py + sanificazione nh3) e `markdown.strip()` (AEV-R7, CTX-R8). *Verifica: grassetto/lista → HTML corretto; HTML inline nel body non passa.*
- [ ] **10.B15 — Render Markdown nei notifier** (~1h): messaggi testuali resi via helper nei notifier esistenti, degradazione mai bloccante (NOT-R8). *Verifica: email formattata, testo pulito sui canali poveri; helper rotto → consegna comunque.*
- [ ] **10.B16 — Messaggi di sistema: catalogo e risoluzione** (~1h): registro chiavi+default nel core, tabella `system_message_template` (solo override), risoluzione unica override→default → punto di traduzione identità → placeholder, usata da tutti i call-site (ADMSG-R7..R10); `user.marked_for_deletion` dichiara `{deletion_due_date}` (USR-R11). *Verifica: override attivo → l'avviso di disattivazione usa il testo custom.*
- [ ] **10.B17 — API message-templates** (~1h): `GET/PUT/DELETE /api/admin/message-templates`, validazione dei placeholder in PUT. *Verifica: DELETE → torna il default; placeholder sconosciuto segnalato.*
- [ ] **10.B18 — API calendario scraper** (~1h): `GET /api/admin/scrapers/calendar?date=` — slot pianificati del giorno + durata media delle run recenti (SCHED-R10). *Verifica: gli slot rispecchiano gli schedule; sospesi esclusi o marcati.*
- [ ] **10.B19 — Scadenza password configurabile (admin)** (~1h): impostazione di sistema `password_expiry` (in `system_settings`, 10.B7) con **opzioni fisse** — **Mai (default)**, 1 mese, 3 mesi, 6 mesi, 1 anno; nuova colonna `password_changed_at` su `users`, aggiornata a ogni cambio password; al login, se la password è più vecchia della finestra configurata, si **forza il cambio** riusando `must_change_password` e il flusso di cambio forzato già esistente. *Verifica: impostata a 1 mese → un utente con password più vecchia di un mese è forzato al cambio al login; "Mai" → nessun forzamento.*

### Da discutere prima di stimare (nessuna implementazione senza discussione)

> ⛔ **Non implementare nulla di questo blocco prima di averlo discusso e deciso con Simone.** È un'idea annotata il 2026-07-27, non un MVP: manca la scelta di fondo, e sceglierla male costa più che rimandarla.

- [ ] **10.D1 — Notifiche per l'admin sui log** *(da discutere)*: oggi i canali di notifica (fase 7) servono **solo l'utente** e solo per eventi di catalogo/carrello; l'admin non riceve nulla, e per accorgersi di un problema deve aprire la pagina dei log e guardare. L'idea è una sezione di notifiche **propria dell'admin**, dove sottoscriversi a ciò che il sistema logga — l'esempio concreto è "mandami una notifica quando il portale logga degli `error`". Il caso reale che la motiva è il blocco di Dragon Store del 2026-07-25: gli errori c'erano nei log dal primo giorno, ma nessuno li ha visti finché Simone non è andato a leggerli.
  >
  > **La decisione aperta è la logica di attivazione**, e le due strade non sono equivalenti:
  > - **Istantanea** — si notifica appena il log viene scritto. Reattiva, ma un guasto ripetitivo genera una raffica: lo scraper che fallisce su 40 watch produrrebbe 40 notifiche identiche. Servirebbe come minimo un raggruppamento o un antiflood.
  > - **A finestre** — un engine dedicato all'admin che gira ogni tot ore, guarda i log del periodo e decide cosa è **significativo** (un errore isolato non lo è, venti errori uguali sì; un errore nuovo mai visto prima probabilmente sì). Più simile a come funzionano già gli alert utente, che sono per digest e non per evento singolo.
  >
  > Altri punti da chiarire quando se ne parla: chi riceve (tutti gli admin? il super-user di fase 9?); quali canali (riuso di quelli di fase 7 o un percorso separato); che granularità di sottoscrizione (per livello, per sorgente, per testo); e se questo debba diventare un **notifier con destinatario admin** dentro l'infrastruttura esistente invece di un sistema parallelo — che è la domanda architetturale più importante delle quattro.

### Frontend

- [ ] **10.F1 — Pagina utenti: lista** (~1h): stato, **ultimo accesso ordinabile**, data marcatura e scadenza, **filtro stato** attivo/disabilitato/in cancellazione. *Verifica: ordinamento e filtro corretti da browser.*
- [ ] **10.F2 — Pagina utenti: azioni** (~1h): creazione, reset password, abilita/disabilita, cancella (soft, con riepilogo e data di eliminazione programmata), **annulla cancellazione**. *Verifica: annullamento porta a disabilitato, mai ad attivo.*
- [ ] **10.F3 — Monitoraggio run: elenco** (~1h): per-scraper: stato corrente, ultima run, elenco run ([scraper-monitoring](../3-features/admin/scraper-monitoring.md)). *Verifica: lo stato di ogni scraper è leggibile a colpo d'occhio.*
- [ ] **10.F4 — Monitoraggio run: drill-down** (~1h): dettaglio per-utente di una run. *Verifica: run partial → l'utente fallito è individuabile col suo errore.*
- [ ] **10.F5 — Trend e contatori** (~1h): grafici durate/http_requests/variazioni per run (componente grafico riusato), contatori 7/30gg. *Verifica: trend leggibili.*
- [ ] **10.F6 — Pagina impostazioni + purge alert** (~1h): form con default e validazioni (incluso il periodo di grazia), azione di purge dello storico alert con conferma. *Verifica: modifica a caldo visibile senza riavvio.*
- [ ] **10.F7 — Dashboard: statistiche globali** (~1h): aggregati di sistema e statistiche notifiche con finestra 7/30gg ([admin-dashboard](../3-features/admin/admin-dashboard.md)). *Verifica: numeri coerenti con i dati.*
- [ ] **10.F8 — Dashboard: ranking utenti** (~1h): dati e carico per utente e per scraper. *Verifica: solo numeri e username, nessun contenuto.*
- [ ] **10.F9 — Composizione messaggi admin** (~1h): textbox Markdown con **anteprima live** (markdown-it + DOMPurify), invio a tutti/un utente, elenco inviati con esiti. *Verifica: anteprima identica al render in-app.*
- [ ] **10.F10 — Storico utente: categorie e render** (~1h): categorie sistema/admin, icona e colore dedicati ai messaggi admin, render Markdown dei messaggi testuali, filtro per categoria (ALERT-R16). *Verifica: broadcast formattato ed evidenziato nello storico di ogni utente.*
- [ ] **10.F11 — Tab messaggi di sistema** (~1h): lista del catalogo con stato default/override, editor Markdown con anteprima e placeholder mostrati, ripristino al default con conferma (ADMSG-R7/R8). *Verifica: override → ripristino → il testo torna quello del core.*
- [ ] **10.F12 — Vista calendario del giorno** (~1h): blocchi per ogni run pianificata (dimensionati sulla durata media), read-only, click sullo scraper → la sua pagina di configurazione, selettore di data (SCHED-R10). *Verifica: gli slot configurati appaiono; il click porta alla config giusta.*
- [ ] **10.F13 — Config plugin-declared degli scraper** (~1h): nella pagina admin dello scraper, **form dinamico** (componente di 7.F1) per le chiavi dichiarate dal plugin nel suo schema — es. le soglie degli adjustments di Dragon Store — accanto ai parametri riservati di 4.F2 ([plugin-configuration](../../docs/3-features/admin/plugin-configuration.md)). *Verifica: soglia Dragon Store cambiata da UI → adjustments ricalcolati di conseguenza.*
- [ ] **10.F14 — Impostazione scadenza password** (~1h): nella pagina impostazioni di sistema (10.F6), un selettore per la **scadenza della password** tra le opzioni fisse — Mai (default), 1 mese, 3 mesi, 6 mesi, 1 anno (10.B19). *Verifica: l'opzione scelta persiste e si riflette sull'enforcement al login.*

## Definition of Done

- [ ] Tutte le [pagine admin](../4-capabilities/frontend/app-shell.md#pagine-admin) esistono e sono usabili.
- [ ] Le domande del [flusso di lettura admin](../3-features/admin/scraper-monitoring.md#flusso-di-lettura-tipico-delladmin) trovano risposta nella UI.
- [ ] L'admin continua a non vedere alcun **contenuto** operativo degli utenti: la dashboard espone solo aggregati e conteggi (DASH-R6).
- [ ] [docs](../../docs/) aggiornata in inglese con la sola parte implementata in questa fase (DOC-12).

## Riferimenti

[admin-experience](../1-business/admin-experience.md) · [scraper-scheduling-and-limits](../../docs/3-features/admin/scraper-scheduling-and-limits.md)
