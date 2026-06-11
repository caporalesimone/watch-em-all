# CI

> **Infrastruttura** · Audience: DevOps, developer.

Pipeline minima (GitHub Actions) su ogni push/PR: esegue i tool già scelti dal progetto — la CI non introduce regole nuove, rende reali quelle esistenti.

## Job

| Job | Comandi | Gate |
|---|---|---|
| Lint backend | `ruff check .` · `ruff format --check .` | bloccante |
| Typecheck backend | `mypy` (strict) | bloccante |
| Test backend | `pytest` (unit + contratto; integrazione con Postgres service) | bloccante |
| Lint frontend | `eslint` · `prettier --check` · `svelte-check` | bloccante |
| Build frontend | `npm run build` (include `build:plugins`) | bloccante |
| Build immagini | `docker compose build` (senza push) | bloccante |

## Note

- Il job di test backend usa un service container Postgres 16: i test di integrazione (catalog delta, alert engine, auth) girano su un DB reale effimero.
- I test di **contratto dei plugin** ([checklist](../plugin-development/checklist-and-testing.md)) girano per ogni plugin abilitato: uno scraper che rompe le regole dell'`external_id` fallisce la CI, non la produzione.
- Nessun deploy automatico: il deploy è manuale (`git pull && docker compose build && up -d`), coerente con la postura self-hosted.
- Politica: `main` sempre verde; le PR non si mergiano con job rossi. Dettagli di processo in [developer-rules](../developer-rules/README.md).
