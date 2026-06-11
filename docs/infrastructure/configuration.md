# Configurazione

> **Infrastruttura** · Audience: DevOps, system engineer. Snippet di configurazione ammessi.

## Principio: DB-first

La configurazione **operativa** vive nel DB ed è editabile dalla UI **senza riavvio**; `config.yaml` contiene solo il **bootstrap** (ciò che serve prima che il DB sia raggiungibile); i **segreti** stanno in `.env`.

| Livello | Dove | Esempi | Cambia con |
|---|---|---|---|
| Bootstrap | `config.yaml` | URL DB, durate token, locale default | restart |
| Segreti | `.env` | credenziali Postgres, SECRET_KEY, password admin iniziale | restart |
| Operativa di sistema | DB `system_settings` | pool scraper, timeout run, retention | UI admin, a caldo |
| Schedule | DB `scraper_schedule` etc. | slot degli scraper, cadenze | UI, a caldo |
| Plugin (admin) | DB `notifier_admin_config` / tabelle plugin | SMTP, politeness, regole sito | UI admin, a caldo |
| Plugin (utente) | DB `notifier_user_config` / tabelle plugin | recapiti, cosa osservare | UI utente, a caldo |
| Attivazione plugin | `manifest.json` (`enabled`) | — | **rebuild + restart** |

## `config.yaml` (bootstrap only)

```yaml
core:
  database_url: "postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}"
  secret_key: "${SECRET_KEY}"
  default_locale: "it"        # lingua dei nuovi utenti
  access_token_ttl_min: 15
  refresh_token_ttl_days: 7
```

L'interpolazione `${VAR}` è risolta dal **loader applicativo** all'avvio leggendo l'ambiente. Niente parametri di plugin qui, niente `enabled` qui: il manifest è l'unica source of truth dell'attivazione.

## `.env` / `.env.example`

Il repo committa `.env.example` senza valori reali:

```dotenv
# Postgres
POSTGRES_USER=watchemall
POSTGRES_PASSWORD=change-me
POSTGRES_DB=watchemall
# Core — generare con: openssl rand -hex 32
SECRET_KEY=change-me
# Admin iniziale (cambio forzato al primo login)
ADMIN_INITIAL_PASSWORD=change-me
```

Solo segreti **core**: i parametri dei notifier (es. SMTP) **non** stanno qui — vivono nel DB, impostati dall'admin dalla UI (compromesso dichiarato: configurabilità da UI > purezza dei segreti, accettabile su installazione privata; i campi secret sono mascherati e write-only).

## Impostazioni di sistema (UI admin, default al primo avvio)

| Chiave | Default | Effetto |
|---|---|---|
| `max_concurrent_scrapers` | 2 | dimensione del pool di esecuzione |
| `scraper_run_timeout_min` | 30 | oltre → run terminata (`timeout`) |
| `catchup_warning_min` | 10 | ritardo oltre cui un'esecuzione è loggata come recupero |
| `log_retention_days` | 90 | retention di system_log e record delle run |

## Multi-lingua

Core: `locales/it.json`, `locales/en.json`. Ogni plugin porta le proprie traduzioni (namespace dedicato): frontend per la UI, backend (notifier) per i testi delle notifiche. La lingua dell'utente è in `users.locale` (default `core.default_locale`), inviata alla UI al login e passata ai notifier. La valuta non è un concetto di configurazione: si rende il simbolo (default €), col codice ISO presente nel contratto Product per il futuro.
