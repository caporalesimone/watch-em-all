# API — Catalogo degli endpoint

> Riferimento **unico e canonico** degli endpoint HTTP del core. Ogni nuovo endpoint va aggiunto qui **prima** dell'implementazione. Convenzioni e Swagger: [README.md](README.md). Le rotte plugin-specific sono registrate dai plugin sotto `/api/plugins/{route_base}` e documentate via OpenAPI dal plugin stesso.

Legenda ruolo: 🌐 pubblico · 👤 user · 🛡 admin

## Auth — [auth](../4-capabilities/core/auth.md)

| Metodo | Path | Ruolo | Body / Query | Risposta | Note |
|---|---|---|---|---|---|
| POST | `/api/auth/login` | 🌐 | `{username, password}` | `{access_token, refresh_token, expires_at}` | rate-limited; `expires_at` = scadenza access |
| POST | `/api/auth/refresh` | 🌐 | `{refresh_token}` | nuova coppia | rotazione jti; riuso → 401 + invalidazione globale |
| POST | `/api/auth/logout` | 👤🛡 | — | 204 | token_version += 1 (tutti i device) |
| POST | `/api/auth/change-password` | 👤🛡 | `{old_password?, new_password}` | 204 | `old_password` obbligatoria nel cambio **normale**, omessa nel cambio **forzato** (must_change_password); azzera must_change_password; invalida i token |

## Profilo (Me)

| Metodo | Path | Ruolo | Body / Query | Risposta | Note |
|---|---|---|---|---|---|
| GET | `/api/me` | 👤🛡 | — | `{id, username, first_name, last_name, role, locale, must_change_password}` | esente dal gate must_change_password (serve al boot della SPA) |
| PATCH | `/api/me` | 👤🛡 | `{locale?}` | 200 | persiste la lingua (V1 English-only: unico valore accettato `en`, selettore non esposto) |
| GET | `/api/me/alert-schedule` | 👤 | — | `AlertSchedule` | |
| PUT | `/api/me/alert-schedule` | 👤 | `{scheduled_time, weekdays}` | 200 | weekdays []=off; cambia stato → effetti baseline dichiarati nella risposta |
| GET | `/api/me/summary-config` | 👤 | — | `SummaryConfig` | |
| PUT | `/api/me/summary-config` | 👤 | `{enabled, frequency, weekday?, scheduled_time}` | 200 | |
| GET | `/api/me/export` | 👤 | `?format=json\|csv` | file download | tutti i propri dati; csv = zip multi-file; secret esclusi — [data-export](../3-features/user/data-export.md) |

## Plugin discovery — [plugin-registry](../4-capabilities/core/plugin-registry.md)

| Metodo | Path | Ruolo | Risposta | Note |
|---|---|---|---|---|
| GET | `/api/plugins` | 👤🛡 | `[{name, type, route_base, icon, display_name}]` | solo abilitati e caricati; niente path interni |

## Catalogo — [catalog-update-service](../4-capabilities/core/catalog-update-service.md)

| Metodo | Path | Ruolo | Body / Query | Note |
|---|---|---|---|---|
| GET | `/api/catalog` | 👤 | `?page=&page_size=&scraper=&search=&sort=&order=&include_removed=` | tabella del Product Picker, paginata server-side; ogni riga include `is_all_time_low` (badge) |
| DELETE | `/api/catalog` | 👤 | — | svuota il catalogo (cascata su membri+storico) |
| DELETE | `/api/catalog/items` | 👤 | `{product_ids}` | rimozione selettiva (cascata) |
| DELETE | `/api/catalog/removed` | 👤 | — | elimina i delistati |

> Lo **scrape-now** non è un endpoint di catalogo: è **per-scraper**, esposto dal plugin sotto `/api/plugins/{route}/scrape-now` (vedi *Rotte plugin-specific* in fondo). Il catalogo si scrive solo via Catalog Update Service, mai da qui.

## Carrelli — [cart-engine](../4-capabilities/core/cart-engine.md)

| Metodo | Path | Ruolo | Body / Query | Note |
|---|---|---|---|---|
| GET | `/api/carts` | 👤 | — | elenco card (con stato calcolato) |
| POST | `/api/carts` | 👤 | `{name, mode, scraper_id?}` | mode immutabile dopo |
| GET | `/api/carts/{id}` | 👤 | — | dettaglio + stato (totali, adjustments, soglia) |
| PATCH | `/api/carts/{id}` | 👤 | `{name?, threshold_pct?, threshold_amount?}` | amount → convertito a pct sul pieno corrente |
| DELETE | `/api/carts/{id}` | 👤 | — | solo il carrello |
| POST | `/api/carts/{id}/items` | 👤 | `{product_ids}` | aggiunta membri |
| DELETE | `/api/carts/{id}/items` | 👤 | `{product_ids}` | rimozione membri |
| PUT | `/api/carts/{id}/alert-types` | 👤 | `{alert_types: [...]}` | set completo; primo tipo → seed baseline, vuoto → delete baseline |

## Storico prezzi — [price-history](../4-capabilities/core/price-history.md)

| Metodo | Path | Ruolo | Query | Note |
|---|---|---|---|---|
| GET | `/api/products/{id}/history` | 👤 | `?range=week\|month\|all` | serie a gradini con flag disponibilità |
| GET | `/api/carts/{id}/history` | 👤 | `?range=` | serie aggregata (composizione corrente) |
| GET | `/api/products/{id}/stats` | 👤 | — | statistiche + indicatore di convenienza, o `insufficient_history` — [price-analytics](../4-capabilities/core/price-analytics.md) |

## Storico alert — [alert-engine](../4-capabilities/core/alert-engine.md)

| Metodo | Path | Ruolo | Body / Query | Note |
|---|---|---|---|---|
| GET | `/api/alerts` | 👤 | `?page=&kind=` | elenco con stato lettura ed esiti di consegna |
| GET | `/api/alerts/{id}` | 👤 | — | payload completo + delivery per canale |
| POST | `/api/alerts/{id}/read` | 👤 | — | marca letto |
| GET | `/api/alerts/unread-count` | 👤 | — | per il badge in dashboard |

## Notifier (utente) — [profile-and-notifiers](../3-features/user/profile-and-notifiers.md)

| Metodo | Path | Ruolo | Body | Note |
|---|---|---|---|---|
| GET | `/api/notifiers` | 👤 | — | per ogni canale: schema utente, `is_set` dei secret, stato composito (disponibile/configurato/attivo) |
| PUT | `/api/notifiers/{plugin_id}/config` | 👤 | `{config}` | chiavi filtrate sullo schema utente; secret assente = non modificare |
| PATCH | `/api/notifiers/{plugin_id}` | 👤 | `{enabled}` | attiva/disattiva senza perdere la config |
| POST | `/api/notifiers/{plugin_id}/test` | 👤 | — | invia notifica di prova; esito sincrono |

## Admin — utenti

| Metodo | Path | Ruolo | Body | Note |
|---|---|---|---|---|
| GET | `/api/admin/users` | 🛡 | `?status=active\|disabled\|deleting&sort=&order=` | elenco con stato, **ultimo accesso** (`last_login_at`, ordinabile — USR-R13), data marcatura e scadenza; `status` = filtro rapido (USR-R14) |
| POST | `/api/admin/users` | 🛡 | `{username, first_name, last_name, role, temp_password}` | nome e cognome obbligatori (USR-R15); must_change_password attivo |
| PATCH | `/api/admin/users/{id}` | 🛡 | `{is_active?, role?}` | disabilitazione → invalidazione token + notifica di cortesia (USR-R11) |
| POST | `/api/admin/users/{id}/reset-password` | 🛡 | `{temp_password}` | + cambio forzato + invalidazione |
| DELETE | `/api/admin/users/{id}` | 🛡 | — | **soft con scadenza**: disattiva + marca in cancellazione + `deletion_due_at` = ora + periodo di grazia, notifica di cortesia; nessun dato eliminato (USR-R7) |
| POST | `/api/admin/users/{id}/restore` | 🛡 | — | annulla la cancellazione: → disabilitato (mai direttamente attivo, USR-R8) |

Il **purge definitivo non ha endpoint**: è il job giornaliero del worker a eliminare gli account scaduti (USR-R9, CRON-R10).

## Admin — scraper e sistema

| Metodo | Path | Ruolo | Body / Query | Note |
|---|---|---|---|---|
| GET | `/api/admin/scrapers` | 🛡 | — | per scraper: schedule, stato (idle/queued/running/sospeso), ultima run |
| PUT | `/api/admin/scrapers/{id}` | 🛡 | `{times, enabled}` → `{scraper_id, times, enabled, last_slot}` | imposta gli slot (input `HH:MM` o `HH:MM:SS`, restituiti **canonici `HH:MM:SS`** — 4.F1, dedup/ordinati; **422** orario non valido) e il flag `enabled`; 1..N slot/giorno; editato dalla pagina **Scrapers → Schedule** |
| GET | `/api/admin/scrapers/calendar` | 🛡 | `?date=YYYY-MM-DD` | **vista calendario del giorno** (SCHED-R10): tutte le run pianificate di tutti gli scraper (slot + durata media recente per dimensionare i blocchi); read-only |
| GET | `/api/admin/scrapers/{id}/runs` | 🛡 | `?page=` | elenco run con contatori |
| GET | `/api/admin/runs/{run_id}` | 🛡 | — | dettaglio per-utente (`scrape_user_log`) |
| GET | `/api/admin/scrapers/{id}/stats` | 🛡 | `?days=30` | serie per i trend (durate, richieste, variazioni) |
| DELETE | `/api/admin/scrapers/{id}/cache` | 🛡 | — | **svuota la cache di scrape** del plugin (CTX-R9); pulsante nella pagina admin del plugin |
| GET | `/api/admin/settings` | 🛡 | — | `SystemSettings` |
| PUT | `/api/admin/settings` | 🛡 | `{scraper_run_timeout_min?, catchup_warning_min?, log_retention_days?, user_deletion_retention_days?}` | effetto immediato, senza riavvio |
| GET | `/api/admin/logs` | 🛡 | `?since=<id>&level=&source=` | polling incrementale: righe con id > since |
| DELETE | `/api/admin/alerts` | 🛡 | `?before=<date>` | purge globale storico alert per data |

## Admin — dashboard di sistema — [admin-dashboard](../3-features/admin/admin-dashboard.md)

| Metodo | Path | Ruolo | Body / Query | Note |
|---|---|---|---|---|
| GET | `/api/admin/dashboard` | 🛡 | `?days=30` | statistiche globali: dimensione (utenti, prodotti, carrelli, storico), run e richieste HTTP del periodo, notifiche con esiti aggregati |
| GET | `/api/admin/dashboard/users` | 🛡 | `?days=30&sort=` | ranking per utente: dati caricati, carico per scraper (richieste, durate), notifiche per canale — solo conteggi e metadati, mai contenuti (DASH-R6) |

## Admin — notifier (config di sistema)

| Metodo | Path | Ruolo | Body | Note |
|---|---|---|---|---|
| GET | `/api/admin/notifiers` | 🛡 | — | per canale: schema admin, `is_set` dei secret, stato, enabled |
| PUT | `/api/admin/notifiers/{plugin_id}/config` | 🛡 | `{config}` | chiavi filtrate sullo schema admin |
| PATCH | `/api/admin/notifiers/{plugin_id}` | 🛡 | `{enabled}` | interruttore globale del canale (PCFG-R8): off = non disponibile per tutti, config utente preservate |
| POST | `/api/admin/notifiers/{plugin_id}/test` | 🛡 | `{...campi utente minimi}` | verifica del canale lato sistema |

## Admin — notifiche agli utenti — [admin-notifications](../3-features/admin/admin-notifications.md)

| Metodo | Path | Ruolo | Body / Query | Note |
|---|---|---|---|---|
| POST | `/api/admin/messages` | 🛡 | `{title, body, user_id?}` | body in **Markdown** (AEV-R7); invio a tutti gli utenti attivi (user_id assente) o a uno specifico; sempre in storico, consegna sui canali abilitati del destinatario |
| GET | `/api/admin/messages` | 🛡 | `?page=` | messaggi inviati con esiti di consegna per destinatario/canale; mai lo stato letto/non letto (ADMSG-R5) |
| GET | `/api/admin/message-templates` | 🛡 | — | catalogo completo: per ogni chiave default, placeholder dichiarati, eventuale override (ADMSG-R7) |
| PUT | `/api/admin/message-templates/{key}` | 🛡 | `{title, body}` | imposta/aggiorna l'override (body Markdown; placeholder sconosciuti segnalati, ADMSG-R8) |
| DELETE | `/api/admin/message-templates/{key}` | 🛡 | — | ripristina il default (cancella l'override, ADMSG-R9) |

## Health — [deployment](../infrastructure/deployment.md)

| Metodo | Path | Ruolo | Risposta | Note |
|---|---|---|---|---|
| GET | `/api/health` | 🌐 | `200 {status, db, version, server_time, worker_heartbeat_age_s}` / `503` | app viva + DB raggiungibile; `server_time` = ISO8601 con offset del fuso d'installazione (clock per la timeline UI, 4.F1); età heartbeat worker informativa |

## Rotte plugin-specific (convenzione)

Registrate dal plugin sotto `/api/plugins/{route_base}`; tipiche per uno scraper:

| Metodo | Path (convenzione) | Ruolo | Note |
|---|---|---|---|
| GET | `/api/plugins/{route}/config-schema/admin` | 🛡 | `ConfigField[]` |
| GET | `/api/plugins/{route}/config-schema/user` | 👤 | `ConfigField[]` |
| GET/PUT | `/api/plugins/{route}/admin-config` | 🛡 | config operativa del plugin |
| POST | `/api/plugins/{route}/test` | 👤🛡 | dry-run, nessuna scrittura; risponde `list[Product]` |
| POST | `/api/plugins/{route}/scrape-now` | 👤 | scrape immediato del **solo utente richiedente** (scrive nel catalogo); **cooldown per-scraper** → **429** col tempo rimanente; 202 + job in background |
| GET | `/api/plugins/{route}/scrape-now` | 👤 | stato del cooldown per l'utente: `{available, available_at, interval_seconds}` (alimenta il conto alla rovescia in UI) |
| GET/POST/DELETE | `/api/plugins/{route}/watches` | 👤 | input dell'utente (cosa osservare) — forma libera del plugin |

Il plugin documenta le proprie route nello schema OpenAPI (`tags=["Plugin: <nome>"]`).
