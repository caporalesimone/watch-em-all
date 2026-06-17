# API — Convenzioni e Swagger

> Audience: developer, integratori. Catalogo completo: [endpoints.md](endpoints.md).

## Convenzioni

- **Prefisso unico `/api/`** per tutti gli endpoint del core; le rotte dei plugin vivono sotto `/api/plugins/{route_base}/…`. Tutto il resto del namespace URL appartiene alla SPA (fallback client-side): nessuna collisione possibile.
- **Autenticazione**: `Authorization: Bearer <access_token>` ([auth](../4-capabilities/core/auth.md)). Endpoint pubblici: solo login, refresh e health.
- **Naming**: JSON in `snake_case`, ovunque (anche `expires_at`).
- **Tipi**: `Decimal` come **stringa** (mai float per i prezzi), `datetime` ISO-8601 UTC, enum come stringhe.
- **Paginazione**: `?page=&page_size=` con risposta `{items, total, page, page_size}` su tutti gli elenchi potenzialmente lunghi (catalogo, storici, run).
- **Errori**: `{detail, code}` con status semantici — `400` validazione, `401` token mancante/scaduto, `403` ruolo o `must_change_password` (code dedicato), `404` non trovato/di altro utente, `409` conflitto di stato (es. scrape-now a catalogo non vuoto), `429` rate limit.
- **Multi-tenancy**: ogni endpoint utente opera implicitamente sull'utente del token; gli id altrui rispondono `404` (mai `403`, per non rivelare esistenza).

## Swagger / OpenAPI

FastAPI genera lo schema OpenAPI automaticamente; è parte del progetto, non un extra:

| URL | Cosa |
|---|---|
| `/api/docs` | **Swagger UI** interattiva |
| `/api/redoc` | Vista ReDoc |
| `/api/openapi.json` | Schema OpenAPI 3 |

Regole:

- Ogni router dichiara `tags` (Auth, Me, Catalog, Carts, History, Alerts, Notifiers, Admin, Plugins, Health): lo Swagger risulta organizzato per aree.
- I modelli di request/response sono **sempre** Pydantic: lo schema è completo per costruzione, senza lavoro extra.
- Le **route dei plugin** sono incluse automaticamente (sono router FastAPI registrati): ogni plugin documenta le proprie con `tags=["Plugin: <nome>"]` e summary — è un requisito della [checklist plugin](../plugin-development/checklist-and-testing.md).
- Auth in Swagger UI: bottone *Authorize* con lo schema Bearer; si incolla l'access token ottenuto dal login (eseguibile da Swagger stessa).
- Postura hobby: la UI Swagger è esposta anche in produzione (utile per il self-hoster); gli endpoint restano protetti da Bearer.

## Versioning

Nessun versioning di URL in V1 (un solo client, stessa release). Se servisse compatibilità: prefisso `/api/v2/` ([future improvements](../future-improvements/README.md)).
