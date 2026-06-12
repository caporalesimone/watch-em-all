# Build system e monorepo

> **Infrastruttura** · Audience: DevOps, developer. Snippet ammessi.

## Monorepo

```
watch-em-all/
├── src/
│   ├── core/        # moduli core backend
│   ├── web/         # app FastAPI (API + static SPA)
│   ├── worker/      # dispatcher + runner
│   ├── frontend/    # app SvelteKit
│   └── plugins/
│       ├── scrapers/<nome>/   # manifest.json, backend/, frontend/
│       └── notifiers/<nome>/
├── packages/
│   ├── web/         # pyproject.toml + Dockerfile del container web
│   └── worker/      # pyproject.toml + Dockerfile del container worker
├── config.yaml
└── .env(.example)
```

- I **plugin non sono package** formali: cartelle auto-scoperte dal registry. Le loro dipendenze Python (es. un browser headless) si dichiarano nel `pyproject.toml` dei package che li caricano (`web` e `worker`), in gruppo opzionale.
- Stack backend: Python 3.12+, Poetry, FastAPI, SQLAlchemy, Pydantic v2.

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
