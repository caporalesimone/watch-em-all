# Watch 'Em All — Documentazione (italiano, spec-ahead)

**Watch 'Em All** è una piattaforma web self-hosted per il monitoraggio di prezzi e disponibilità di prodotti su siti e-commerce, con notifiche quando i carrelli dell'utente raggiungono il risparmio desiderato.

> **Questa non è più la source of truth completa.** La documentazione della parte **implementata** (fasi 0–6, alert in-app inclusi) è stata migrata nella wiki inglese canonica [`../docs/`](../docs/README.md). Qui, in `docs-ita/`, resta **solo la parte spec-ahead** — le fette non ancora costruite (fase 7+: consegna sui canali/notifier, summary, export, analytics, messaggi admin) — più il **roadmap** ([`development-flow/`](development-flow/README.md)) e i [`future-improvements/`](future-improvements/README.md). Ogni file spec-ahead dichiara in testa il proprio equivalente inglese per la parte già rilasciata. Questa cartella **si assottiglia a ogni fase** man mano che il contenuto migra in inglese, e viene ritirata a v1.

> **Postura del progetto**: personal/hobby project, max ~5 utenti contemporanei. Si adottano pattern moderni (plugin-first, JWT, container, API tipizzate) ma **senza pretese enterprise/production-ready**: alcune semplificazioni (HTTP, auth leggera, no HA) sono scelte consapevoli. Vedi [Security Posture](../docs/2-architecture/security-posture.md).

## Come è organizzata la documentazione (modello a 4 layer)

La documentazione è stratificata per **audience**: ogni layer ha regole precise su cosa può contenere. Qui sotto, per ciascun layer, **cosa resta spec-ahead** in `docs-ita/` e **dove trovare l'implementato** in `../docs/`.

| Layer | Cartella | Cosa resta qui (spec-ahead) | Implementato (in `../docs/`) |
|---|---|---|---|
| **1 — Business** | [`1-business/`](1-business/) | Le sole **capacità non ancora costruite** (anello di notifica, canali di consegna, storico) dentro [product-overview](1-business/product-overview.md), [use-cases](1-business/use-cases.md), [personas-and-roles](1-business/personas-and-roles.md), [user-experience](1-business/user-experience.md), [admin-experience](1-business/admin-experience.md), [glossary](1-business/glossary.md) | [`../docs/1-business/`](../docs/1-business/product-overview.md) |
| **2 — Architettura** | [`2-architecture/`](2-architecture/) | [notification-architecture](2-architecture/notification-architecture.md) (residuo: consegna sui canali); i residui spec-ahead di [data-and-multitenancy](2-architecture/data-and-multitenancy.md), [plugin-architecture](2-architecture/plugin-architecture.md), [scheduling-and-execution](2-architecture/scheduling-and-execution.md) | [`../docs/2-architecture/`](../docs/2-architecture/system-overview.md) |
| **3 — Feature** | [`3-features/`](3-features/) | **admin**: [admin-dashboard](3-features/admin/admin-dashboard.md), [admin-notifications](3-features/admin/admin-notifications.md), [scraper-monitoring](3-features/admin/scraper-monitoring.md), [user-management](3-features/admin/user-management.md) (residuo) · **plugins**: [notifier-plugin](3-features/plugins/notifier-plugin.md) · **user**: [alerts-and-notifications](3-features/user/alerts-and-notifications.md), [summary-report](3-features/user/summary-report.md), [data-export](3-features/user/data-export.md), [price-analytics](3-features/user/price-analytics.md), e i residui di [carts](3-features/user/carts.md), [price-history](3-features/user/price-history.md), [profile-and-notifiers](3-features/user/profile-and-notifiers.md) | [`../docs/3-features/`](../docs/3-features/user/carts.md) |
| **4 — Capability** | [`4-capabilities/`](4-capabilities/) | **contracts**: [alert-event](4-capabilities/contracts/alert-event.md), [config-field](4-capabilities/contracts/config-field.md), [scheduling-models](4-capabilities/contracts/scheduling-models.md) (residuo) · **core**: [alert-engine](4-capabilities/core/alert-engine.md), [price-analytics](4-capabilities/core/price-analytics.md), [summary-report](4-capabilities/core/summary-report.md), e i residui di [plugin-context](4-capabilities/core/plugin-context.md), [price-history](4-capabilities/core/price-history.md) · **database**: [schema](4-capabilities/database/schema.md) (residuo) · **frontend**: [app-shell](4-capabilities/frontend/app-shell.md) (residuo) | [`../docs/4-capabilities/`](../docs/4-capabilities/database/schema.md) |

Regole di layer (invariabili): Layer 1 solo testo descrittivo (al più 3 diagrammi Mermaid di alto livello, niente codice); Layer 2 testo + Mermaid, niente codice; Layer 3 testo + Mermaid, niente codice; Layer 4 unico layer con pseudocodice e riferimenti al codice. Piccole deroghe (snippet di configurazione, esempi minimi) sono ammesse ma vanno tenute al minimo — la regola completa è in [developer-rules/documentation/rules.md](../docs/developer-rules/documentation/rules.md).

## Sezioni trasversali

| Sezione | Dove vive ora | Contenuto |
|---|---|---|
| [`api/`](api/endpoints.md) | qui (spec-ahead) | Solo le **rotte in arrivo** (fase 6+): [endpoints.md](api/endpoints.md). Gli endpoint implementati e le convenzioni/Swagger sono in [`../docs/api/`](../docs/api/README.md). |
| [`plugin-development/`](plugin-development/README.md) | qui | Guida per chi sviluppa nuovi plugin: [README](plugin-development/README.md), [checklist-and-testing](plugin-development/checklist-and-testing.md), [scraper-development-guide](plugin-development/scraper-development-guide.md), [notifier-development-guide](plugin-development/notifier-development-guide.md). |
| [`implemented-plugins/`](implemented-plugins/README.md) | qui (spec-ahead) | I plugin **non ancora rilasciati**: i notifier [email](implemented-plugins/notifiers/email.md) e [discord](implemented-plugins/notifiers/discord.md). Lo scraper Dragon Store, già rilasciato, è in [`../docs/implemented-plugins/`](../docs/implemented-plugins/README.md). |
| [`development-flow/`](development-flow/README.md) | qui | Il piano di sviluppo per piccoli MVP: fasi ordinate (00–13), checkbox di avanzamento. Roadmap completa del progetto. |
| [`future-improvements/`](future-improvements/README.md) | qui | Miglioramenti consapevolmente rimandati, con motivazione e trigger: [platform](future-improvements/platform.md), [plugins-and-notifications](future-improvements/plugins-and-notifications.md), [observability-and-data](future-improvements/observability-and-data.md). |
| `infrastructure/` | **migrato** | Deployment, dev container, configurazione, build system, backup/restore, CI: ora in [`../docs/infrastructure/`](../docs/infrastructure/build-system.md). |
| `developer-rules/` | **migrato** | Regole di codice e qualità (backend, frontend, infrastruttura, plugin, docs): ora in [`../docs/developer-rules/`](../docs/developer-rules/README.md). |
| [`../docs/`](../docs/README.md) | canonica | **Documentazione inglese**: la wiki canonica del sistema implementato (fasi 0–5); cresce alla chiusura di ogni fase (DOC-12) e a v1 sostituisce `docs-ita/`. |

## Percorsi di lettura consigliati

- **Stakeholder / "cosa fa il prodotto?"** → [Layer 1 (inglese)](../docs/1-business/product-overview.md), in particolare [use-cases.md](../docs/1-business/use-cases.md). Per la visione ancora da realizzare: [product-overview spec-ahead](1-business/product-overview.md).
- **Architetto SW** → [Layer 2 — system overview (inglese)](../docs/2-architecture/system-overview.md), poi i [Layer 3 (inglese)](../docs/3-features/user/carts.md) di interesse; per la parte notifiche non ancora costruita: [notification-architecture](2-architecture/notification-architecture.md).
- **System engineer / DevOps** → [Layer 2 — system overview](../docs/2-architecture/system-overview.md) + [`../docs/infrastructure/`](../docs/infrastructure/build-system.md).
- **Developer core** → Layer 2 → Layer 3 → [Layer 4 (inglese)](../docs/4-capabilities/database/schema.md) del modulo assegnato + [`../docs/developer-rules/`](../docs/developer-rules/README.md) + [`../docs/api/`](../docs/api/README.md). Per sapere **cosa fare adesso**: [`development-flow/`](development-flow/README.md).
- **Plugin developer** → [`plugin-development/`](plugin-development/README.md) (autosufficiente, con rimandi mirati).

## Principi trasversali del progetto

- **Plugin-first full-stack**: ogni plugin è un'unità autonoma con backend Python e frontend Svelte; il core orchestra e non conosce la logica interna dei plugin.
- **Multi-tenant**: ogni dato operativo ha `user_id`; isolamento completo tra utenti.
- **Pydantic ovunque**: tutti i modelli di I/O usano Pydantic v2.
- **Config DB-first**: la configurazione operativa vive nel DB ed è editabile dalla UI; `config.yaml` solo per il bootstrap.
- **English-first**: lo sviluppo avviene **in inglese**; alle traduzioni si penserà in futuro. L'impalcatura i18n è però obbligatoria fin dal primo giorno: ogni stringa statica vive dietro una chiave nelle cartelle **`i18n/`** (core e ogni singolo plugin), che inizialmente contengono il solo `en.json` — le lingue future si aggiungono lì. **`en.json` deve sempre esistere ed essere completo**: è il fallback quando una lingua di sistema manca. Mai stringhe cablate o costruite per concatenazione. Multilingua completo: [future improvement](future-improvements/platform.md).
- **Ogni plugin è configurabile a due livelli**: amministratore (parametri di sistema, uguali per tutti) e utente (parametri personali).
- **Requisiti con ID prefissati** (es. `CART-R3`, `CRON-R9`): citabili in commit, issue e test.

## Convenzioni dei documenti

- Lingua: italiano. Termini tecnici e identificatori in inglese.
- Ogni documento dichiara in testa **layer** e **audience**, e — se spec-ahead — l'equivalente inglese già rilasciato.
- I requisiti usano il prefisso del modulo (`AUTH-R1`, `SCR-R4`, …).
- I rimandi tra documenti sono sempre link relativi.
