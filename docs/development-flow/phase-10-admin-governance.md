# Fase 10 — Governo admin

> Stato: ☐ da iniziare · Prerequisiti: Fase 4 (Fase 9 consigliata: più dati da osservare) · [Indice del flusso](README.md)

## Obiettivo

Completare la plancia dell'admin: statistiche e drill-down delle run, limiti di sistema modificabili a caldo, gestione utenti completa, manutenzione (retention e purge).

## Risultato apprezzabile

L'admin apre il monitoraggio e capisce in un colpo d'occhio quanto lavorano gli scraper (durate, richieste, trend), scende nel dettaglio per-utente di una run lenta, regola il pool e la retention dalla UI, crea e gestisce gli account.

## MVP

### Backend

- [ ] **10.B1 — API gestione utenti** (~2h): create/reset/disable/delete con cascate e invalidazione token ([user-management](../3-features/admin/user-management.md)). *Verifica: utente disabilitato → fuori entro la scadenza dell'access token.*
- [ ] **10.B2 — API run e statistiche** (~2h): elenco run paginato, dettaglio per-utente, `GET /api/admin/scrapers/{id}/stats` (serie per i trend). *Verifica: dati coerenti con le run accumulate.*
- [ ] **10.B3 — Impostazioni di sistema + retention** (~3h): `system_settings` con seed dei default, effetto a caldo (pool, timeout, soglia recuperi); retention automatica di log e run nel worker ([system-logs-and-maintenance](../3-features/admin/system-logs-and-maintenance.md)). *Verifica: pool a 1 → due scraper dovuti girano in sequenza.*
- [ ] **10.B4 — Purge storico alert** (~1h): `DELETE /api/admin/alerts?before=`. *Verifica: notifiche vecchie sparite per tutti, recenti intatte.*
- [ ] **10.B5 — API dashboard di sistema** (~3h): `GET /api/admin/dashboard` e `/dashboard/users` — aggregati globali, ranking per utente e per (utente, scraper), statistiche notifiche; include `http_requests` per-utente su `scrape_user_log` ([admin-dashboard](../3-features/admin/admin-dashboard.md)). *Verifica: i totali tornano con i dati delle tabelle; nessun contenuto utente nelle risposte (DASH-R6).*

### Frontend

- [ ] **10.F1 — Pagina utenti** (~2h): lista con stato, creazione, reset password, disabilita/riabilita, elimina con conferma a cascata. *Verifica: flussi completi da browser.*
- [ ] **10.F2 — Pagina monitoraggio run** (~3h): per-scraper: stato corrente, ultima run, elenco run, drill-down per-utente ([scraper-monitoring](../3-features/admin/scraper-monitoring.md)). *Verifica: run partial → l'utente fallito è individuabile col suo errore.*
- [ ] **10.F3 — Trend e contatori** (~2h): grafici durate/http_requests/variazioni per run (componente grafico riusato), contatori 7/30gg. *Verifica: trend leggibili.*
- [ ] **10.F4 — Pagina impostazioni + purge** (~2h): form impostazioni di sistema con default e validazioni; azione di purge con conferma. *Verifica: modifica a caldo visibile senza riavvio.*
- [ ] **10.F5 — Pagina dashboard di sistema** (~3h): statistiche globali, ranking utenti (dati e carico per scraper), statistiche notifiche con finestra 7/30gg ([admin-dashboard](../3-features/admin/admin-dashboard.md)). *Verifica: ranking coerenti con i dati; solo numeri e username, nessun contenuto.*

## Definition of Done

- [ ] Tutte le [pagine admin](../4-capabilities/frontend/app-shell.md#pagine-admin) esistono e sono usabili.
- [ ] Le domande del [flusso di lettura admin](../3-features/admin/scraper-monitoring.md#flusso-di-lettura-tipico-delladmin) trovano risposta nella UI.
- [ ] L'admin continua a non vedere alcun **contenuto** operativo degli utenti: la dashboard espone solo aggregati e conteggi (DASH-R6).

## Riferimenti

[admin-experience](../1-business/admin-experience.md) · [scraper-scheduling-and-limits](../3-features/admin/scraper-scheduling-and-limits.md)
