# Developer Rules — Backend (Python)

> Vincolanti per tutto il codice Python (core e plugin). Tooling: [build-system](../../infrastructure/build-system.md) · CI: [ci](../../infrastructure/ci.md).

## Stile e tipi

- **BE-1** — Python 3.12+. `ruff check` e `ruff format` puliti; `mypy --strict` pulito. Niente `# type: ignore` senza commento che spiega il perché.
- **BE-2** — Type hints **ovunque** (firme complete); `Any` solo ai confini con librerie non tipizzate, mai nei contratti.
- **BE-3** — Naming: `snake_case` per funzioni/variabili, `PascalCase` per classi, costanti `UPPER_CASE`. Identificatori in inglese; i commenti possono essere in italiano.
- **BE-4** — Funzioni corte e a un livello di astrazione; estrarre prima di superare ~40 righe. Niente classi "manager" tuttofare.

## Modelli e dati

- **BE-5** — **Pydantic v2 a ogni confine di I/O**: request/response API, payload persistiti come JSON, contratti dei plugin. Mai dict non tipizzati nei contratti pubblici.
- **BE-6** — **Prezzi sempre `Decimal`**, mai float. Serializzazione JSON: Decimal come stringa, datetime ISO-8601 **UTC**.
- **BE-7** — SQLAlchemy: query sempre filtrate per `user_id` del token nelle tabelle operative (multi-tenancy: DB-R1); vincoli di unicità dichiarati nello schema, non solo "garantiti dal codice".
- **BE-8** — Niente SQL in stringhe formattate con input esterno: solo parametri bound.

## Errori e logging

- **BE-9** — Eccezioni specifiche, mai `except Exception` muto: o si gestisce, o si rilancia, o si logga con contesto. Le run (scrape/alert/summary) catturano al confine e registrano nei log di sistema.
- **BE-10** — Log: messaggi azionabili con identificativi (user_id, plugin_id, run_id), **mai contenuti operativi degli utenti** (titoli prodotti, payload notifiche) nel `system_log`.
- **BE-11** — Gli errori API seguono il formato `{detail, code}` e gli status delle [convenzioni](../../api/README.md).

## Concorrenza e tempo

- **BE-12** — Niente thread/process spawn fuori dallo [Scraper Runner](../../4-capabilities/core/scraper-pool.md); la concorrenza è una proprietà del sistema, non delle feature — e tra scraper non esiste: l'esecuzione è seriale (SCHED-R6).
- **BE-13** — `datetime.now(tz=UTC)` o l'orologio applicativo iniettabile; mai `utcnow()` naïve. Le comparazioni di schedule usano l'ora server documentata.
- **BE-14** — Hash deterministici (SHA-256) per qualunque identità persistita; **mai** `hash()` built-in.
- **BE-21** — **Backend sincrono.** Endpoint `def` (eseguiti da FastAPI nel suo threadpool), `Session` SQLAlchemy classica, psycopg in modalità sincrona; **niente `async def`/asyncio** nel core né nei plugin (i metodi del contratto plugin — `run_for_user`, `send`, `run_test` — sono sincroni, e `context.http` è un client sincrono). La concorrenza vive **solo** dove è una proprietà del sistema: il threadpool del web e il [runner a thread](../../4-capabilities/core/scraper-pool.md) del worker. Scelta dichiarata per la postura ≤5-10 utenti: a questa scala l'async non dà throughput e complicherebbe runner, advisory lock e contratto plugin; si scala con il tuning di threadpool e pool di connessioni, e l'evoluzione verso async/parallelismo è un [future improvement](../../future-improvements/platform.md) se il progetto cresce. Il dispatcher resta non bloccante accodando al runner (CRON-R5), non con asyncio.

## Test

- **BE-15** — Logica pura (delta, diff alert, soglie, slot dovuti) coperta da **unit test tabellari**: sono il cuore della correttezza del prodotto.
- **BE-16** — Integrazione su Postgres effimero (la CI fornisce il service) per catalog update, auth, cascade.
- **BE-17** — I test non toccano mai la rete: fixture salvate; il client HTTP del contesto si finge.
- **BE-18** — Un bug corretto = un test che lo avrebbe preso.

## API

- **BE-19** — Router con `tags`, modelli Pydantic per request/response (lo Swagger è completo per costruzione), endpoint registrato in [endpoints.md](../../api/endpoints.md) **prima** dell'implementazione.
- **BE-20** — Endpoint utente: l'id implicito è quello del token; risorse altrui → `404`. Endpoint admin: `require_admin`, mai dati operativi degli utenti.
