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
│   ├── web/         # Dockerfile + entrypoint del container web
│   ├── worker/      # Dockerfile + entrypoint del container worker
│   └── ops/         # Dockerfile dell'immagine ops (postgres:16 + script)
├── ops/             # script backup/export/restore (backup-and-restore.md)
├── deploy/
│   └── compose.yml  # compose di release (immagini GHCR): allegato alla release come deploy kit
├── backups/         # archivi prodotti dagli script (gitignorata)
├── docs/            # documentazione di progetto (italiano, source of truth)
├── docs-eng/        # documentazione inglese incrementale (DOC-12)
├── docker-compose.yml  # compose di sviluppo (build: dai sorgenti)
├── pyproject.toml   # UNICO, alla root: dipendenze backend + gruppi opzionali
├── poetry.lock      # un solo lockfile per tutto il backend
├── CHANGELOG.md     # storia delle release (SemVer, INF-19)
├── config.yaml      # default, cucinato nelle immagini; override locale via mount
└── .env(.example)
```

Le **immagini pubblicate** (`watch-em-all-web`, `-worker`, `-ops`) sono buildate e pushate su GHCR dal workflow di publish a ogni tag ([ci](ci.md)); l'utente finale installa con il solo deploy kit, senza sorgenti ([deployment](deployment.md), INF-17).

- **Un solo `pyproject.toml` alla root** (un solo `poetry.lock`): `web` e `worker` condividono lo stesso ambiente Python e caricano gli stessi plugin, quindi le dipendenze sono uniche — un secondo lockfile creerebbe solo drift da tenere allineato a mano. I Dockerfile dei package installano dalla root, ciascuno selezionando i **gruppi opzionali** che gli servono.
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
