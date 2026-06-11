# Database — Schema logico

> **Layer 4 — Capability** · Audience: developer · Riferimenti tecnici ammessi. Architettura: [data-and-multitenancy](../../2-architecture/data-and-multitenancy.md).

Motore **PostgreSQL 16**, accesso via SQLAlchemy, validazione I/O Pydantic v2. Schema creato idempotentemente all'avvio da web e worker; tabelle dei plugin create dai plugin stessi.

## Auth

| Tabella | Colonne | Note |
|---|---|---|
| `users` | id, username **UNIQUE**, password_hash, role (`admin`\|`user`), is_active, locale, must_change_password, token_version, refresh_jti, created_at | [auth](../core/auth.md): refresh_jti = ultimo refresh emesso (rotazione); token_version = invalidazione globale |

## Catalogo e storico

| Tabella | Colonne | Note |
|---|---|---|
| `products` | id, user_id FK, plugin_id, external_id, url, name, image_url, extra_json, currency, price_current, price_original, discount_pct, is_available, removed, first_seen_at, last_seen_at | **UNIQUE (user_id, plugin_id, external_id)** = identità del prodotto; catalogo per-utente |
| `price_history` | id, product_id FK **CASCADE**, user_id, price_current, price_original, discount_pct, is_available, recorded_at | Append-only; entry su cambio prezzo **o** disponibilità; INDEX (product_id, recorded_at); **nessuna retention** |

## Carrelli

| Tabella | Colonne | Note |
|---|---|---|
| `carts` | id, user_id FK, name, mode (`cross`\|`scraper_specific`), scraper_id (null se cross), threshold_pct (null = nessuna soglia), created_at | mode immutabile; soglia come colonna (1:1) |
| `cart_members` | cart_id FK **CASCADE**, product_id FK **CASCADE** | **UNIQUE (cart_id, product_id)**; la cascata da products realizza CAT-R8 |
| `cart_alert_types` | cart_id FK **CASCADE**, alert_type | **Presenza riga = tipo abilitato** (niente colonna enabled); UNIQUE (cart_id, alert_type) |

## Notifiche

| Tabella | Colonne | Note |
|---|---|---|
| `alert_schedule` | user_id PK/FK, scheduled_time, weekdays (int[], 0=lun), last_run_date | cadenza per-utente; [] = off |
| `summary_config` | user_id PK/FK, enabled, frequency (`weekly`\|`monthly`), weekday, scheduled_time, last_run_date | opt-in; monthly = giorno 1 |
| `alert_snapshot` | user_id FK, cart_id FK **CASCADE**, snapshot_json, taken_at — **PK (user_id, cart_id)** | baseline **per-carrello**: seed all'abilitazione, avanza a ogni run, delete alla disabilitazione |
| `alert_log` | id, user_id FK, kind (`alert_digest`\|`summary`\|`admin_message`), admin_message_id FK (null se non admin), payload_json, created_at, read_at (null = non letto) | sempre scritto; INDEX (user_id, created_at); purge admin per data; kind determina la categoria (sistema/admin) |
| `admin_message` | id, target_user_id FK (null = broadcast a tutti), title, body, created_at | il messaggio master; una riga `alert_log` per destinatario; gli esiti si leggono via `alert_delivery` |
| `alert_delivery` | id, alert_id FK **CASCADE**, plugin_id (null = nessun canale), status (`delivered`\|`failed`\|`skipped_no_notifier`), error_message, delivered_at | **un esito per canale** |
| `notifier_admin_config` | plugin_id PK, config_json, **enabled** (default true), updated_at | parametri di sistema del canale; enabled = interruttore globale admin (PCFG-R8) |
| `notifier_user_config` | plugin_id, user_id FK, **enabled** (flag attivazione), config_json — PK (plugin_id, user_id) | disattivare ≠ cancellare la config |

## Scheduling e monitoraggio

| Tabella | Colonne | Note |
|---|---|---|
| `scraper_schedule` | scraper_id PK, times (time[]), enabled, last_slot (timestamptz) | 1..N slot/giorno; last_slot = ultimo slot eseguito |
| `scrape_run` | run_id, scraper_id, trigger, slot, started_at, finished_at, status, users_processed, products_found, products_new, price_changes, products_removed, products_excluded, http_requests, error_message | una riga per run; INDEX (scraper_id, started_at); retention |
| `scrape_user_log` | run_id FK **CASCADE**, user_id, started_at, finished_at, products_found, products_new, price_changes, http_requests, status, error_message | dettaglio per utente; http_requests attribuite all'utente in lavorazione (run mono-thread); retention |
| `system_settings` | key PK, value_json, updated_at | impostazioni runtime ([SystemSettings](../contracts/scheduling-models.md)); seed dei default al primo avvio |
| `system_log` | id (PK incrementale, cursore del polling), created_at, level, source (`worker`\|`scraper`\|`notifier`\|`alert`\|`summary`), message, context_json | INDEX (id); retention; mai contenuti operativi degli utenti |

## Tabelle dei plugin

Naming `plugin_<nomeplugin>_<nometabella>` (underscore: gli identificatori SQL col trattino richiederebbero quoting). Create **dal plugin** in `initialize()`, idempotentemente. Il core non le conosce; tipicamente contengono gli **input per-utente** dello scraper e i suoi parametri. Esempi reali in [implemented-plugins/](../../implemented-plugins/).

## Regole trasversali

- **DB-R1** — Ogni tabella operativa ha `user_id`: ogni query applicativa filtra per l'utente del token (multi-tenancy).
- **DB-R2** — Cancellazione utente → cascata completa dei suoi dati.
- **DB-R3** — Serializzazione nei campi `*_json`: `Decimal` come stringa, `datetime` ISO-8601 UTC; i confronti "è cambiato?" avvengono sul dato deserializzato.
- **DB-R4** — **Migrazioni V1**: schema additivo con `CREATE ... IF NOT EXISTS`; per i breaking change, script SQL manuali documentati nel changelog — **mai** drop&recreate dell'intero schema: `price_history` non è ricostruibile. (Alembic: [future improvement](../../future-improvements/README.md).)
- **DB-R5** — Backup: dump del DB o snapshot del volume, responsabilità dell'host ([deployment](../../infrastructure/deployment.md)).
- **DB-R6** — Ispezione dev: Adminer, solo profilo `dev`.
