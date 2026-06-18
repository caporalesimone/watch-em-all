# Fase 2 — Plugin system

> Stato: 🚧 in corso — i 7 MVP sono implementati e verificati (test backend, type-check frontend, build CI); resta la **DoD provata dal vivo** nel dev container · Prerequisiti: Fase 1 · [Indice del flusso](README.md)

## Obiettivo

L'integrazione dinamica dei plugin, backend e frontend: la spina dorsale dell'architettura plugin-first. Si costruisce con un **plugin demo** usa-e-getta, prima di avere uno scraper vero — così il meccanismo si testa isolato.

## Risultato apprezzabile

Si crea una cartella con un manifest e due file: al rebuild il plugin **appare da solo** in sidebar con la sua pagina e la sua route API nello Swagger. Lo si disabilita dal manifest: sparisce ovunque.

## MVP

### Backend

- [x] **2.B1 — Parser del manifest** (~1h): parsing + validazioni (type/cartella, `api_version`, name univoco, `plugin_id` coincidente) ([manifest-reference](../plugin-development/manifest-reference.md)). *Verifica: unit test su manifest validi e rotti.* ✅ `tests/test_plugin_manifest.py`
- [x] **2.B2 — Registry con load isolato** (~1h): caricamento dei plugin abilitati, rifiuto esplicito del singolo plugin rotto senza far cadere l'app ([plugin-registry](../4-capabilities/core/plugin-registry.md)). *Verifica: manifest rotto → log error, app su, gli altri plugin vivi.* ✅ `tests/test_plugin_registry.py`
- [x] **2.B3 — Plugin Context minimo** (~1h): db (tabelle proprie), logger, config; niente http per ora ([plugin-context](../4-capabilities/core/plugin-context.md)). *Verifica: il demo crea una sua tabella in `initialize()`.* ✅ `tests/test_plugin_context.py` (logger→stdout e config vuoto sono stub di fase dichiarati)
- [x] **2.B4 — Discovery API + route plugin** (~1h): `GET /api/plugins` (senza path interni), router del TP sotto `/api/plugins/tp-scraper` con tag Swagger. *Verifica: endpoint del demo visibile e funzionante in Swagger.* ✅ `tests/test_plugin_discovery.py`

### Frontend

- [x] **2.F1 — Registro generato dal build** (~1h): step `build:plugins` → `plugin-registry.ts` generato dai manifest ([build-system](../infrastructure/build-system.md)). *Verifica: plugin abilitato/disabilitato → registro coerente al rebuild.* ✅ vitest `scripts/build-plugins.test.mjs`
- [x] **2.F2 — Route dinamica + sidebar** (~1h): fetch `/api/plugins`, route dinamica catch-all `plugins/[...rest]`, voce in sidebar con icona ([plugin-discovery](../4-capabilities/frontend/plugin-discovery.md)). *Verifica: pagina del demo raggiungibile dalla sidebar* (conferma live nel dev container).
- [x] **2.F3 — Gestione mismatch bundle/runtime** (~1h): plugin nel bundle ma assente a runtime (voce nascosta) e viceversa (segnalazione esplicita). *Verifica: i due casi di mismatch gestiti senza errori in console* (conferma live nel dev container).

## Definition of Done

- [ ] Il plugin demo è completamente dinamico: nessun riferimento a "demo" nel codice core o di build.
- [ ] `enabled: false` + rebuild → il plugin non esiste da nessuna parte (API, sidebar, bundle).
- [ ] Un secondo plugin demo copia-incollato appare anch'esso senza toccare nulla.
- [ ] [docs](../../docs/) aggiornata in inglese con la sola parte implementata in questa fase (DOC-12).

## Riferimenti

[plugin-architecture](../2-architecture/plugin-architecture.md) · [dynamic-integration](../3-features/plugins/dynamic-integration.md) · [build-system](../infrastructure/build-system.md)
