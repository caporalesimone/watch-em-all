# Configuration

> **Infrastructure** · Audience: DevOps, system engineer. Config snippets allowed.

## Principle: DB-first

**Operational** configuration lives in the DB and is editable from the UI **without a restart**; `config.yaml` holds only the **bootstrap** (what is needed before the DB is reachable); the **secrets** stay in `.env`.

| Level | Where | Examples | Changes with |
|---|---|---|---|
| Bootstrap | `config.yaml` (default **in the image**; local override via mount) | DB URL, token lifetimes, default locale | restart |
| Secrets | `.env` | Postgres credentials, WEA_SECRET_KEY, initial admin password | restart |
| System operational | DB `system_settings` | run timeout, retention, user-deletion grace period | admin UI, hot |
| Schedule | DB `scraper_schedule` etc. | scraper slots, cadences | UI, hot |
| Plugin (admin) | DB `notifier_admin_config` / plugin tables | SMTP, politeness, site rules | admin UI, hot |
| Plugin (user) | DB `notifier_user_config` / plugin tables | contact details, what to watch | user UI, hot |
| Plugin activation | `manifest.json` (`enabled`) | — | **rebuild + restart** |

## `config.yaml` (bootstrap only)

```yaml
core:
  database_url: "postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}"
  secret_key: "${WEA_SECRET_KEY}"
  default_locale: "en"        # locale of new users (V1 English-first)
  access_token_ttl_min: 15
  refresh_token_ttl_days: 7
```

The `${VAR}` interpolation is resolved by the **application loader** at startup reading the environment. No plugin parameters here, no `enabled` here: the manifest is the single source of truth for activation.

The default file is **included in the** `web` and `worker` **images** (the pull-based installation requires no local file, [deployment](deployment.md)): whoever wants to customise it creates a `config.yaml` next to the compose and **mounts it over** the image's one (`./config.yaml:/app/config.yaml:ro`) — the mount wins, the image stays the fallback. The local override, if present, is included in the [backup archive](backup-and-restore.md).

## `.env` / `.env.example`

The repo commits `.env.example` without real values:

```dotenv
# Postgres
POSTGRES_USER=watchemall
POSTGRES_PASSWORD=change-me
POSTGRES_DB=watchemall
# Core — generate with: openssl rand -hex 32
WEA_SECRET_KEY=change-me
# Initial admin (forced change at first login)
WEA_ADMIN_INITIAL_PASSWORD=change-me
# Installation timezone (entered times interpreted here; stored timestamps in UTC)
TZ=Europe/Rome
```

Besides the secrets, `.env` carries a few **non-secret environment variables** consumed by the containers: **`TZ`** (the installation's timezone) and **`WEA_VERSION`** — the **image version chosen by the operator** (the tag to run, [deployment](deployment.md)). Note: `WEA_VERSION` is the choice of *which* image to use, **not** the product version: that is baked into the image at build from `git describe` and exposed at `GET /api/health` (source of truth = git tag, [ci](ci.md#single-source-of-truth-for-the-version)). `TZ` defines the installation's **single timezone**: the times entered by admin/user (scraper slots, alert and summary times) are **interpreted in this timezone**, while the **persisted** timestamps stay UTC (BE-13); the app does the conversions explicitly (`zoneinfo`), without relying on the process's ambiguous local time. Default `Europe/Rome`; a single timezone for the whole installation (per-user: [future improvement](../future-improvements/README.md)).

As for the real secrets: the notifier parameters (e.g. SMTP) are **not** here — they live in the DB, set by the admin from the UI (declared trade-off: UI configurability > secret purity, acceptable on a private installation; the secret fields are masked and write-only).

## System settings (admin UI, defaults at first startup)

| Key | Default | Effect |
|---|---|---|
| `scraper_run_timeout_min` | 30 | past it → run terminated (`timeout`) |
| `catchup_warning_min` | 10 | delay past which an execution is logged as a catch-up |
| `log_retention_days` | 90 | retention of system_log and run records |
| `user_deletion_retention_days` | 30 | grace period between marking and the automatic purge of accounts (USR-R9) |

## Multi-language

**English-first**: development is in English, translations will come in the future. The language files live in the **`i18n/`** folders — core: `i18n/en.json`; each plugin: `frontend/i18n/` (UI) and `backend/i18n/` (notifier, notification texts) — initially with `en.json` only, **always present and complete**: it is the fallback when the system language is missing in a plugin. Future languages are added in the same folders. The user's language is in `users.locale` (default `core.default_locale`, V1: `en`), sent to the UI at login and passed to the notifiers. Currency is not a configuration concept: the symbol is rendered (default €), with the ISO code present in the Product contract for the future.
