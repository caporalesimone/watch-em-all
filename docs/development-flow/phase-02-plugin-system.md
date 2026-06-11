# Fase 2 — Plugin system

> Stato: ☐ da iniziare · Prerequisiti: Fase 1 · [Indice del flusso](README.md)

## Obiettivo

L'integrazione dinamica dei plugin, backend e frontend: la spina dorsale dell'architettura plugin-first. Si costruisce con un **plugin demo** usa-e-getta, prima di avere uno scraper vero — così il meccanismo si testa isolato.

## Risultato apprezzabile

Si crea una cartella con un manifest e due file: al rebuild il plugin **appare da solo** in sidebar con la sua pagina e la sua route API nello Swagger. Lo si disabilita dal manifest: sparisce ovunque.

## MVP

### Backend

- [ ] **2.B1 — Manifest e registry** (~3h): parser+validazioni del manifest (type/cartella, api_version, name univoco, `plugin_id` coincidente), load isolato con rifiuto esplicito ([plugin-registry](../4-capabilities/core/plugin-registry.md), [manifest-reference](../plugin-development/manifest-reference.md)). *Verifica: manifest rotto → log error, app su.*
- [ ] **2.B2 — Plugin Context minimo** (~2h): db (tabelle proprie), logger, config; niente http per ora ([plugin-context](../4-capabilities/core/plugin-context.md)). *Verifica: il demo crea una sua tabella in `initialize()`.*
- [ ] **2.B3 — Discovery API + route plugin** (~2h): `GET /api/plugins` (senza path interni), router del demo sotto `/api/plugins/demo` con tag Swagger. *Verifica: endpoint del demo visibile e funzionante in Swagger.*

### Frontend

- [ ] **2.F1 — Registro generato dal build** (~2h): step `build:plugins` → `plugin-registry.ts` generato dai manifest ([build-system](../infrastructure/build-system.md)). *Verifica: plugin abilitato/disabilitato → registro coerente al rebuild.*
- [ ] **2.F2 — Discovery runtime e mounting** (~3h): fetch `/api/plugins`, route dinamica, voce in sidebar con icona, gestione mismatch bundle/runtime ([plugin-discovery](../4-capabilities/frontend/plugin-discovery.md)). *Verifica: pagina del demo raggiungibile dalla sidebar.*

## Definition of Done

- [ ] Il plugin demo è completamente dinamico: nessun riferimento a "demo" nel codice core o di build.
- [ ] `enabled: false` + rebuild → il plugin non esiste da nessuna parte (API, sidebar, bundle).
- [ ] Un secondo plugin demo copia-incollato appare anch'esso senza toccare nulla.

## Riferimenti

[plugin-architecture](../2-architecture/plugin-architecture.md) · [dynamic-integration](../3-features/plugins/dynamic-integration.md) · [build-system](../infrastructure/build-system.md)
