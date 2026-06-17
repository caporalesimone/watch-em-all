# Build system e monorepo

> **Infrastruttura** · Audience: DevOps, developer. Snippet ammessi.

## Monorepo

```
watch-em-all/
├── .devcontainer/   # ambiente di sviluppo zero-install (dev-container.md)
├── src/
│   ├── core/        # moduli core backend
│   ├── web/         # app FastAPI (API + static SPA)
│   ├── worker/      # dispatcher + runner
│   ├── frontend/    # app SvelteKit
│   └── plugins/
│       ├── scrapers/<nome>/   # manifest.json, backend/, frontend/
│       └── notifiers/<nome>/
├── packages/
│   ├── app/         # Dockerfile + entrypoint dell'immagine app (ruoli web|worker via command)
│   └── ops/         # Dockerfile dell'immagine ops (postgres:16 + script)
├── ops/             # script backup/export/restore (backup-and-restore.md)
├── deploy/
│   └── compose.yml  # compose di release (immagini GHCR): deploy kit nel repo, scaricato al tag
├── backups/         # archivi prodotti dagli script (gitignorata)
├── docs/            # documentazione inglese — cresce fase per fase (canonica a v1)
├── docs-ita/        # documentazione italiana — source of truth durante la transizione
├── docker-compose.yml  # compose di sviluppo (build: dai sorgenti)
├── pyproject.toml   # UNICO, alla root: dipendenze backend + gruppi opzionali
├── poetry.lock      # un solo lockfile per tutto il backend
├── CHANGELOG.md     # storia delle release (SemVer, INF-19)
├── config.yaml      # default, cucinato nelle immagini; override locale via mount
└── .env(.example)
```

Le **immagini pubblicate** sono **due** — `watch-em-all` (l'app: ruoli `web` e `worker`) e `watch-em-all-ops` (`postgres:16` + script) — buildate e pushate su GHCR dal workflow di publish a ogni tag ([ci](ci.md)); l'utente finale installa con il solo deploy kit, senza sorgenti ([deployment](deployment.md), INF-17).

- **Un'unica immagine app per `web` e `worker`** (`packages/app/`): condividono lo stesso codice, lo stesso `pyproject.toml`/`poetry.lock` e gli stessi plugin — sono **un'unica applicazione con due ruoli**, non due componenti. Il ruolo si sceglie col **comando d'avvio** (`command: ["web"]` / `["worker"]`), via un entrypoint che smista; così si builda e si versiona **un solo artefatto** invece di due quasi identici. `ops` resta separata perché ha una base diversa (`postgres:16`).
- **Un solo `pyproject.toml` alla root** (un solo `poetry.lock`): le dipendenze del backend sono uniche — un secondo lockfile creerebbe solo drift da tenere allineato a mano. Il Dockerfile dell'app installa dalla root selezionando i **gruppi opzionali** che servono. Il campo `version` di `pyproject.toml` (e di `package.json`) è un **placeholder inerte**: non pubblichiamo pacchetti, e la versione del prodotto ha un'unica source of truth nel **tag git**, calcolata a build da `git describe` ed esposta su `/api/health` ([ci](ci.md#fonte-unica-della-versione-source-of-truth)).
- I **plugin non sono package** formali: cartelle auto-scoperte dal registry. Le loro dipendenze Python (es. un browser headless) si dichiarano nel `pyproject.toml` unico, in un **gruppo opzionale** dedicato.
- Stack backend: Python 3.12+, Poetry, FastAPI, SQLAlchemy, Pydantic v2.
- Stack frontend: **Node 22 LTS**, **SvelteKit 2** (Svelte 5, runes), **Tailwind CSS 4**, **svelte-i18n**, Vite. Versioni major fissate al giorno 1 (progetto nuovo, nessun debito di migrazione).

## Build frontend unificato

Un solo processo Vite include app e plugin abilitati:

```
npm run build
  ├── 1. build:plugins        # legge tutti i manifest.json in src/plugins/**
  │       ├── filtra enabled=true con frontend.entry
  │       └── genera src/frontend/src/generated/plugin-registry.ts
  └── 2. vite build           # SvelteKit (adapter-static, SPA fallback)
```

Regole:

- Il registro generato non si scrive **mai** a mano (`FDISC-R1`).
- Aggiungere un plugin = creare la cartella con manifest valido + `frontend/index.ts` conforme: **zero modifiche** a build o routing.
- I plugin importano i componenti core via `$lib/components` (build unico: nessun problema cross-bundle).
- **Conseguenza operativa**: cambiare `enabled` richiede rebuild dell'immagine `web` (il bundle è cucinato nel Dockerfile: `RUN npm run build`) + restart. Documentato anche in [deployment](deployment.md).

## Tooling backend

```toml
[tool.ruff]
line-length = 100
lint.select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.mypy]
strict = true
```

Le regole d'uso (cosa deve passare prima di un merge) sono in [developer-rules/backend](../developer-rules/backend/rules.md); la pipeline che le esegue in [ci.md](ci.md).
