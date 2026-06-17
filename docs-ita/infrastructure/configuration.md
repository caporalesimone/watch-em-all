# Configurazione

> **Infrastruttura** · Audience: DevOps, system engineer. Snippet di configurazione ammessi.

## Principio: DB-first

La configurazione **operativa** vive nel DB ed è editabile dalla UI **senza riavvio**; `config.yaml` contiene solo il **bootstrap** (ciò che serve prima che il DB sia raggiungibile); i **segreti** stanno in `.env`.

| Livello | Dove | Esempi | Cambia con |
|---|---|---|---|
| Bootstrap | `config.yaml` (default **nell'immagine**; override locale via mount) | URL DB, durate token, locale default | restart |
| Segreti | `.env` | credenziali Postgres, SECRET_KEY, password admin iniziale | restart |
| Operativa di sistema | DB `system_settings` | timeout run, retention, periodo di grazia cancellazione utenti | UI admin, a caldo |
| Schedule | DB `scraper_schedule` etc. | slot degli scraper, cadenze | UI, a caldo |
| Plugin (admin) | DB `notifier_admin_config` / tabelle plugin | SMTP, politeness, regole sito | UI admin, a caldo |
| Plugin (utente) | DB `notifier_user_config` / tabelle plugin | recapiti, cosa osservare | UI utente, a caldo |
| Attivazione plugin | `manifest.json` (`enabled`) | — | **rebuild + restart** |

## `config.yaml` (bootstrap only)

```yaml
core:
  database_url: "postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}"
  secret_key: "${SECRET_KEY}"
  default_locale: "en"        # lingua dei nuovi utenti (V1 English-first)
  access_token_ttl_min: 15
  refresh_token_ttl_days: 7
```

L'interpolazione `${VAR}` è risolta dal **loader applicativo** all'avvio leggendo l'ambiente. Niente parametri di plugin qui, niente `enabled` qui: il manifest è l'unica source of truth dell'attivazione.

Il file di default è **incluso nelle immagini** `web` e `worker` (l'installazione pull-based non richiede alcun file locale, [deployment](deployment.md)): chi vuole personalizzarlo crea `config.yaml` accanto al compose e lo **monta sopra** quello dell'immagine (`./config.yaml:/app/config.yaml:ro`) — il mount vince, l'immagine resta il fallback. L'override locale, se presente, entra nell'[archivio di backup](backup-and-restore.md).

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
# Fuso orario dell'installazione (orari inseriti interpretati qui; timestamp salvati in UTC)
TZ=Europe/Rome
```

Oltre ai segreti, il `.env` porta alcune **variabili d'ambiente non segrete** consumate dai container: **`TZ`** (fuso dell'installazione) e **`WEA_VERSION`** — la **versione dell'immagine scelta dall'operatore** (il tag da far girare, [deployment](deployment.md)). Attenzione: `WEA_VERSION` è la scelta di *quale* immagine usare, **non** la versione del prodotto: quella è cucinata nell'immagine a build da `git describe` ed esposta su `GET /api/health` (source of truth = tag git, [ci](ci.md#fonte-unica-della-versione-source-of-truth)). `TZ` definisce il **fuso unico** dell'installazione: gli orari inseriti da admin/utente (slot degli scraper, orari di alert e summary) sono **interpretati in questo fuso**, mentre i timestamp **persistiti restano UTC** (BE-13); l'app fa le conversioni in modo esplicito (`zoneinfo`), senza affidarsi all'ora locale ambigua del processo. Default `Europe/Rome`; un solo fuso per tutta l'installazione (per-utente: [future improvement](../future-improvements/platform.md)).

Quanto ai segreti veri: i parametri dei notifier (es. SMTP) **non** stanno qui — vivono nel DB, impostati dall'admin dalla UI (compromesso dichiarato: configurabilità da UI > purezza dei segreti, accettabile su installazione privata; i campi secret sono mascherati e write-only).

## Impostazioni di sistema (UI admin, default al primo avvio)

| Chiave | Default | Effetto |
|---|---|---|
| `scraper_run_timeout_min` | 30 | oltre → run terminata (`timeout`) |
| `catchup_warning_min` | 10 | ritardo oltre cui un'esecuzione è loggata come recupero |
| `log_retention_days` | 90 | retention di system_log e record delle run |
| `user_deletion_retention_days` | 30 | periodo di grazia tra marcatura e purge automatico degli account (USR-R9) |

## Multi-lingua

**English-first**: lo sviluppo è in inglese, le traduzioni verranno in futuro. I file di lingua vivono nelle cartelle **`i18n/`** — core: `i18n/en.json`; ogni plugin: `frontend/i18n/` (UI) e `backend/i18n/` (notifier, testi delle notifiche) — inizialmente con il solo `en.json`, **sempre presente e completo**: è il fallback quando la lingua di sistema manca in un plugin. Le lingue future si aggiungono nelle stesse cartelle. La lingua dell'utente è in `users.locale` (default `core.default_locale`, V1: `en`), inviata alla UI al login e passata ai notifier. La valuta non è un concetto di configurazione: si rende il simbolo (default €), col codice ISO presente nel contratto Product per il futuro.
