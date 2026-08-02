# API — Catalogo degli endpoint (spec-ahead)

> Endpoint **non ancora rilasciati** (fase 6+). Gli endpoint già implementati (fasi 0–5) vivono nella wiki inglese canonica: [`docs/api/endpoints.md`](../../docs/api/endpoints.md). Questo file conserva **solo le rotte in arrivo**: ogni nuovo endpoint va aggiunto qui **prima** dell'implementazione, e migrato nella wiki inglese al rilascio. Convenzioni e Swagger: [README.md](../../docs/api/README.md). Le rotte plugin-specific sono registrate dai plugin sotto `/api/plugins/{route_base}` e documentate via OpenAPI dal plugin stesso.

Legenda ruolo: 🌐 pubblico · 👤 user · 🛡 admin

## Profilo (Me) — pianificazione e export

| Metodo | Path | Ruolo | Body / Query | Risposta | Note |
|---|---|---|---|---|---|
| GET | `/api/me/summary-config` | 👤 | — | `SummaryConfig` | |
| PUT | `/api/me/summary-config` | 👤 | `{enabled, frequency, weekday?, scheduled_time}` | 200 | |
| GET | `/api/me/export` | 👤 | `?format=json\|csv` | file download | tutti i propri dati; csv = zip multi-file; secret esclusi — [data-export](../3-features/user/data-export.md) |

## Catalogo — pulizia (mutazioni) — [catalog-update-service](../../docs/4-capabilities/core/catalog-update-service.md)

| Metodo | Path | Ruolo | Body / Query | Note |
|---|---|---|---|---|
| DELETE | `/api/catalog` | 👤 | — | svuota il catalogo (cascata su membri+storico) |
| DELETE | `/api/catalog/items` | 👤 | `{product_ids}` | rimozione selettiva (cascata) |
| DELETE | `/api/catalog/removed` | 👤 | — | elimina i delistati |

> La lettura del catalogo (`GET /api/catalog`) è già implementata (vedi wiki inglese). Lo **scrape-now** non è un endpoint di catalogo: è **per-scraper**, esposto dal plugin sotto `/api/plugins/{route}/scrape-now`. Il catalogo si scrive solo via Catalog Update Service, mai da qui.

## Storico prezzi — [price-history](../4-capabilities/core/price-history.md)

| Metodo | Path | Ruolo | Query | Note |
|---|---|---|---|---|
| GET | `/api/products/{id}/history` | 👤 | `?range=week\|month\|all` | serie a gradini con flag disponibilità |
| GET | `/api/carts/{id}/history` | 👤 | `?range=` | serie aggregata (composizione corrente) |
| GET | `/api/products/{id}/stats` | 👤 | — | statistiche + indicatore di convenienza, o `insufficient_history` — [price-analytics](../4-capabilities/core/price-analytics.md) |

## Notifier (utente) — [profile-and-notifiers](../3-features/user/profile-and-notifiers.md)

| Metodo | Path | Ruolo | Body | Note |
|---|---|---|---|---|
| GET | `/api/notifiers` | 👤 | — | per ogni canale: schema utente, `is_set` dei secret, stato composito (disponibile/configurato/attivo) |
| PUT | `/api/notifiers/{plugin_id}/config` | 👤 | `{config}` | chiavi filtrate sullo schema utente; secret assente = non modificare |
| PATCH | `/api/notifiers/{plugin_id}` | 👤 | `{enabled}` | attiva/disattiva senza perdere la config |

Un invio di prova lato utente **non esiste più** (10.X4): aveva senso finché il recapito lo scriveva l'utente in quella pagina, ma da 10.B23/10.B25 il recapito **è** l'account e si è già dimostrato funzionante portando la password con cui quella persona è entrata. Quel che restava era una sonda sulla configurazione SMTP del server, che l'utente non può comunque toccare: la prova vive solo lato admin, dove da 10.B28 è diventata la **validazione** del canale (`POST /api/admin/notifiers/{plugin_id}/validate`).

## Admin — utenti (ciclo di vita)

> Creazione ed elenco account (`POST`/`GET /api/admin/users`) sono già implementati (vedi wiki inglese). Il ciclo di vita ricco arriva in fase 10.

| Metodo | Path | Ruolo | Body | Note |
|---|---|---|---|---|
| PATCH | `/api/admin/users/{id}` | 🛡 | `{is_active?, role?}` | disabilitazione → invalidazione token + notifica di cortesia (USR-R11) |
| POST | `/api/admin/users/{id}/reset-password` | 🛡 | — | password generata e spedita (10.B24) + cambio forzato + invalidazione |
| DELETE | `/api/admin/users/{id}` | 🛡 | — | **soft con scadenza**: disattiva + marca in cancellazione + `deletion_due_at` = ora + periodo di grazia, notifica di cortesia; nessun dato eliminato (USR-R7) |
| POST | `/api/admin/users/{id}/restore` | 🛡 | — | annulla la cancellazione: → disabilitato (mai direttamente attivo, USR-R8) |
| DELETE | `/api/admin/users/{id}/purge` | 🛡 | — | **cancellazione definitiva subito** su un account già marcato (USR-R9b): `204`, `409 not_being_deleted` se non marcato, `403 cannot_target_self`, `500 purge_failed` se un plugin rifiuta |

Il purge automatico resta il job giornaliero del worker sugli account scaduti (USR-R9, CRON-R10); l'endpoint qui sopra è la **stessa** distruzione con un altro innesco, non una seconda implementazione. Anche l'elenco `GET /api/admin/users` guadagna in questa fase i filtri `?status=active\|disabled\|deleting` (USR-R14) e l'ordinamento per **ultimo accesso** (`last_login_at`, USR-R13).

## Admin — scraper (storico e monitoraggio) — [scraper-scheduling-and-limits](../../docs/3-features/admin/scraper-scheduling-and-limits.md)

> Elenco/schedule (`GET`/`PUT /api/admin/scrapers`), svuota cache, config riservata (`GET/PATCH …/config`), settings, log e feature-flag sono già implementati (vedi wiki inglese).

| Metodo | Path | Ruolo | Body / Query | Note |
|---|---|---|---|---|
| GET | `/api/admin/scrapers/calendar` | 🛡 | `?date=YYYY-MM-DD` | **vista calendario del giorno** (SCHED-R10): tutte le run pianificate di tutti gli scraper (slot + durata media recente per dimensionare i blocchi); read-only |
| GET | `/api/admin/scrapers/{id}/runs` | 🛡 | `?page=` | elenco run con contatori |
| GET | `/api/admin/runs/{run_id}` | 🛡 | — | dettaglio per-utente (`scrape_user_log`) |
| GET | `/api/admin/scrapers/{id}/stats` | 🛡 | `?days=30` | serie per i trend (durate, richieste, variazioni) |
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
| PATCH | `/api/admin/notifiers/{plugin_id}` | 🛡 | `{enabled}` | interruttore globale del canale (PCFG-R8): off = non disponibile per tutti, config utente preservate. Accendere un canale **non validato** → `422 not_validated` (10.B28) |
| POST | `/api/admin/notifiers/{plugin_id}/validate` | 🛡 | — | manda un messaggio vero all'account dell'admin (10.B25); se il server lo accetta, le impostazioni risultano **validate** (NOT-R9) → `{ok, error, channel}`. Config incompleta → `422 config_incomplete`; un rifiuto non registra nulla |

## Admin — notifiche agli utenti — [admin-notifications](../3-features/admin/admin-notifications.md)

| Metodo | Path | Ruolo | Body / Query | Note |
|---|---|---|---|---|
| POST | `/api/admin/messages` | 🛡 | `{title, body, user_id?}` | body in **Markdown** (AEV-R7); invio a tutti gli utenti attivi (user_id assente) o a uno specifico; sempre in storico, consegna sui canali abilitati del destinatario |
| GET | `/api/admin/messages` | 🛡 | `?page=` | messaggi inviati con esiti di consegna per destinatario/canale; mai lo stato letto/non letto (ADMSG-R5) |
| GET | `/api/admin/message-templates` | 🛡 | — | catalogo completo: per ogni chiave default, placeholder dichiarati, eventuale override (ADMSG-R7) |
| PUT | `/api/admin/message-templates/{key}` | 🛡 | `{title, body}` | imposta/aggiorna l'override (body Markdown; placeholder sconosciuti segnalati, ADMSG-R8) |
| DELETE | `/api/admin/message-templates/{key}` | 🛡 | — | ripristina il default (cancella l'override, ADMSG-R9) |

## Rotte plugin-specific (convenzione, parte non ancora implementata)

Registrate dal plugin sotto `/api/plugins/{route_base}`. Le rotte già implementate per uno scraper (`test`, `scrape-now` POST/GET, `watches`) sono documentate nella wiki inglese; qui restano le parti della convenzione **non ancora realizzate** (config del plugin, che arriva con le pagine admin in fase 7+/9):

| Metodo | Path (convenzione) | Ruolo | Note |
|---|---|---|---|
| GET | `/api/plugins/{route}/config-schema/admin` | 🛡 | `ConfigField[]` |
| GET | `/api/plugins/{route}/config-schema/user` | 👤 | `ConfigField[]` |
| GET/PUT | `/api/plugins/{route}/admin-config` | 🛡 | config operativa del plugin |

Il plugin documenta le proprie route nello schema OpenAPI (`tags=["Plugin: <nome>"]`).
