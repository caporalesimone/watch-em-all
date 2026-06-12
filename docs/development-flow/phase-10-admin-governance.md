# Fase 10 — Governo admin

> Stato: ☐ da iniziare · Prerequisiti: Fase 4 (Fase 9 consigliata: più dati da osservare) · [Indice del flusso](README.md)

## Obiettivo

Completare la plancia dell'admin: statistiche e drill-down delle run, limiti di sistema modificabili a caldo, gestione utenti completa, manutenzione (retention e purge).

## Risultato apprezzabile

L'admin apre il monitoraggio e capisce in un colpo d'occhio quanto lavorano gli scraper (durate, richieste, trend), vede la giornata pianificata nella vista calendario, scende nel dettaglio per-utente di una run lenta, regola timeout e retention dalla UI, crea e gestisce gli account.

## MVP

### Backend

- [ ] **10.B1 — API gestione utenti** (~3h): create/reset/disable con invalidazione token; `last_login_at` aggiornato al login ed esposto in lista (ordinabile, USR-R13); filtro `?status=` (USR-R14); delete **soft con scadenza** (disattiva + `deletion_marked_at` + `deletion_due_at` + notifica di cortesia), restore = annulla cancellazione (→ disabilitato), login con codice `account_disabled` a credenziali corrette ([user-management](../3-features/admin/user-management.md), AUTH-R10). *Verifica: utente disabilitato → fuori entro la scadenza dell'access token; delete non elimina alcun dato e fissa la scadenza; ordinamento per ultimo accesso corretto.*
- [ ] **10.B1b — Purge automatico utenti** (~3h): hook `delete_user_data` su BasePlugin (default no-op) e nei plugin con tabelle proprie; job giornaliero del worker (CRON-R10) che elimina gli account con `deletion_due_at` scaduta: plugin in sequenza, cascata core solo se tutti ok, fallimento → utente resta marcato + errore in system_log, retry il giorno dopo (USR-R9/R10). *Verifica: account scaduto → eliminato alla manutenzione giornaliera, nessuna riga residua core o plugin; plugin che fallisce → dati intatti e nuovo tentativo il giorno dopo; account non scaduto → intatto.*
- [ ] **10.B2 — API run e statistiche** (~2h): elenco run paginato, dettaglio per-utente, `GET /api/admin/scrapers/{id}/stats` (serie per i trend). *Verifica: dati coerenti con le run accumulate.*
- [ ] **10.B3 — Impostazioni di sistema + retention** (~3h): `system_settings` con seed dei default (incluso `user_deletion_retention_days`), effetto a caldo (timeout, soglia recuperi, periodo di grazia pro-futuro); retention automatica di log e run nella manutenzione giornaliera del worker ([system-logs-and-maintenance](../3-features/admin/system-logs-and-maintenance.md)). *Verifica: timeout ridotto a caldo → la run lunga successiva è terminata; periodo di grazia cambiato → vale solo per le nuove marcature.*
- [ ] **10.B4 — Purge storico alert** (~1h): `DELETE /api/admin/alerts?before=`. *Verifica: notifiche vecchie sparite per tutti, recenti intatte.*
- [ ] **10.B5 — API dashboard di sistema** (~3h): `GET /api/admin/dashboard` e `/dashboard/users` — aggregati globali, ranking per utente e per (utente, scraper), statistiche notifiche; include `http_requests` per-utente su `scrape_user_log` ([admin-dashboard](../3-features/admin/admin-dashboard.md)). *Verifica: i totali tornano con i dati delle tabelle; nessun contenuto utente nelle risposte (DASH-R6).*
- [ ] **10.B6 — Interruttore globale notifier** (~1h): colonna `enabled` su `notifier_admin_config`, `PATCH /api/admin/notifiers/{id}`; canale off = non disponibile per tutti, config utente preservate (PCFG-R8). *Verifica: canale disabilitato → consegne saltate per tutti, riattivato → tornano senza riconfigurare.*
- [ ] **10.B7 — API messaggi admin** (~3h): tabella `admin_message`, kind `admin_message`/`system_message` su `alert_log`, `POST/GET /api/admin/messages` — invio a tutti/un utente sulla pipeline notifiche esistente, esiti per destinatario/canale ([admin-notifications](../3-features/admin/admin-notifications.md)). *Verifica: utente senza canali riceve il messaggio in-app (ADMSG-R2); l'admin non vede lo stato letto/non letto (ADMSG-R5).*
- [ ] **10.B8 — Helper Markdown nel plugin context** (~2h): `markdown.to_html()` (markdown-it-py + sanificazione nh3) e `markdown.strip()`; render dei messaggi testuali nei notifier esistenti via helper, con degradazione mai bloccante (AEV-R7, NOT-R8, CTX-R8). *Verifica: body con grassetto/lista → HTML corretto nell'email, testo pulito sui canali poveri; HTML inline nel body non passa.*
- [ ] **10.B9 — Catalogo messaggi di sistema** (~3h): registro chiavi+default nel core, tabella `system_message_template` (solo override), `GET/PUT/DELETE /api/admin/message-templates`; funzione di risoluzione unica (override→default → punto di traduzione identità → placeholder) usata da tutti i call-site dei `system_message` (ADMSG-R7..R10); il template `user.marked_for_deletion` dichiara `{deletion_due_date}` (USR-R11). *Verifica: override attivo → l'avviso di disattivazione usa il testo custom; DELETE → torna il default; placeholder sconosciuto segnalato in PUT.*
- [ ] **10.B10 — API calendario scraper** (~1h): `GET /api/admin/scrapers/calendar?date=` — slot pianificati di tutti gli scraper del giorno + durata media delle run recenti (SCHED-R10). *Verifica: gli slot rispecchiano gli schedule correnti; scraper sospesi esclusi o marcati.*

### Frontend

- [ ] **10.F1 — Pagina utenti** (~3h): lista con stato, **ultimo accesso ordinabile**, data marcatura e scadenza; **filtro stato** attivo/disabilitato/in cancellazione; creazione, reset password, icone abilita/disabilita e cancella (soft, con riepilogo e data di eliminazione programmata); **annulla cancellazione** per i marcati. *Verifica: flussi completi da browser; annullamento porta a disabilitato, mai ad attivo; ordinamento per ultimo accesso individua gli inattivi.*
- [ ] **10.F2 — Pagina monitoraggio run** (~3h): per-scraper: stato corrente, ultima run, elenco run, drill-down per-utente ([scraper-monitoring](../3-features/admin/scraper-monitoring.md)). *Verifica: run partial → l'utente fallito è individuabile col suo errore.*
- [ ] **10.F3 — Trend e contatori** (~2h): grafici durate/http_requests/variazioni per run (componente grafico riusato), contatori 7/30gg. *Verifica: trend leggibili.*
- [ ] **10.F4 — Pagina impostazioni + purge alert** (~2h): form impostazioni di sistema con default e validazioni (incluso il periodo di grazia della cancellazione utenti); azione di purge dello storico alert con conferma. *Verifica: modifica a caldo visibile senza riavvio.*
- [ ] **10.F5 — Pagina dashboard di sistema** (~3h): statistiche globali, ranking utenti (dati e carico per scraper), statistiche notifiche con finestra 7/30gg ([admin-dashboard](../3-features/admin/admin-dashboard.md)). *Verifica: ranking coerenti con i dati; solo numeri e username, nessun contenuto.*
- [ ] **10.F6 — Pagina notifiche agli utenti + categorie nello storico** (~4h): composizione Markdown con **textbox + anteprima live** (markdown-it + DOMPurify), invio (tutti/un utente), elenco inviati con esiti; toggle enabled nella pagina notifier; nello storico utente: categorie sistema/admin, icona e colore dedicati ai messaggi admin, render Markdown dei messaggi testuali, filtro per categoria (ALERT-R16). *Verifica: messaggio broadcast con formattazione visibile, renderizzato ed evidenziato nello storico di ogni utente; anteprima identica al render in-app.*
- [ ] **10.F7 — Tab messaggi di sistema** (~2h): lista del catalogo con stato default/override, editor Markdown con anteprima e placeholder disponibili mostrati, ripristino al default con conferma (ADMSG-R7/R8). *Verifica: override → ripristino → il testo torna quello del core.*
- [ ] **10.F8 — Vista calendario del giorno** (~2h): la giornata con un blocco per ogni run pianificata di ogni scraper (dimensionato sulla durata media), read-only, click sullo scraper → la sua pagina di configurazione, selettore di data (SCHED-R10). *Verifica: gli slot configurati appaiono nel calendario; il click porta alla config giusta.*

## Definition of Done

- [ ] Tutte le [pagine admin](../4-capabilities/frontend/app-shell.md#pagine-admin) esistono e sono usabili.
- [ ] Le domande del [flusso di lettura admin](../3-features/admin/scraper-monitoring.md#flusso-di-lettura-tipico-delladmin) trovano risposta nella UI.
- [ ] L'admin continua a non vedere alcun **contenuto** operativo degli utenti: la dashboard espone solo aggregati e conteggi (DASH-R6).

## Riferimenti

[admin-experience](../1-business/admin-experience.md) · [scraper-scheduling-and-limits](../3-features/admin/scraper-scheduling-and-limits.md)
