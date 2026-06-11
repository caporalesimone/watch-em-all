# Watch 'Em All — Documentazione di progetto

**Watch 'Em All** è una piattaforma web self-hosted per il monitoraggio di prezzi e disponibilità di prodotti su siti e-commerce, con notifiche quando i carrelli dell'utente raggiungono il risparmio desiderato.

> **Postura del progetto**: personal/hobby project, max ~5 utenti contemporanei. Si adottano pattern moderni (plugin-first, JWT, container, API tipizzate) ma **senza pretese enterprise/production-ready**: alcune semplificazioni (HTTP, auth leggera, no HA) sono scelte consapevoli. Vedi [Security Posture](2-architecture/security-posture.md).

## Come è organizzata la documentazione (modello a 4 layer)

La documentazione è stratificata per **audience**: ogni layer ha regole precise su cosa può contenere.

| Layer | Cartella | Contenuto | Regole | Audience |
|---|---|---|---|---|
| **1** | [`1-business/`](1-business/) | Business, use case, esperienza utente/admin | **Solo testo descrittivo** ad alto livello. Niente diagrammi, niente codice. | Stakeholder, chiunque |
| **2** | [`2-architecture/`](2-architecture/) | Architettura di sistema, feature ad alto livello | Testo + **diagrammi Mermaid**. Niente codice. | Architetti SW, system engineer |
| **3** | [`3-features/`](3-features/) | Feature dettagliate (user / admin / plugin) | Testo + **diagrammi Mermaid**. Niente codice. | Architetti, analisti, developer |
| **4** | [`4-capabilities/`](4-capabilities/) | Capability tecniche, contratti, schema dati | **Unico layer con pseudocodice** e riferimenti al codice. | Developer |

Piccole deroghe (snippet di configurazione, esempi minimi per chiarezza) sono ammesse ma vanno tenute al minimo — la regola completa è in [developer-rules/documentation/rules.md](developer-rules/documentation/rules.md).

## Sezioni trasversali

| Sezione | Contenuto | Audience |
|---|---|---|
| [`api/`](api/) | Convenzioni API, integrazione Swagger, **catalogo completo degli endpoint** | Developer, integratori |
| [`infrastructure/`](infrastructure/) | Deployment Docker, configurazione, build system, CI | DevOps, system engineer |
| [`plugin-development/`](plugin-development/) | Guida per chi sviluppa nuovi plugin (scraper e notifier) | Plugin developer |
| [`implemented-plugins/`](implemented-plugins/) | Documentazione dei plugin reali: Dragon Store, Email, Discord | Developer |
| [`developer-rules/`](developer-rules/) | Regole di codice e qualità: backend, frontend, infrastruttura, plugin, docs | Tutti i developer |
| [`development-flow/`](development-flow/README.md) | Il piano di sviluppo per piccoli MVP: fasi ordinate, checkbox di avanzamento | Developer, owner |
| [`future-improvements/`](future-improvements/) | Miglioramenti rimandati, con motivazione e prerequisiti | Architetti, owner |

## Percorsi di lettura consigliati

- **Stakeholder / "cosa fa il prodotto?"** → [Layer 1](1-business/product-overview.md), in particolare [use-cases.md](1-business/use-cases.md).
- **Architetto SW** → [Layer 2](2-architecture/system-overview.md) tutto, poi i [Layer 3](3-features/) di interesse.
- **System engineer / DevOps** → [Layer 2 — system overview](2-architecture/system-overview.md) + [`infrastructure/`](infrastructure/).
- **Developer core** → Layer 2 → Layer 3 → [Layer 4](4-capabilities/) del modulo assegnato + [`developer-rules/`](developer-rules/) + [`api/`](api/). Per sapere **cosa fare adesso**: [`development-flow/`](development-flow/README.md).
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
- Ogni documento dichiara in testa **layer** e **audience**.
- I requisiti usano il prefisso del modulo (`AUTH-R1`, `SCR-R4`, …).
- I rimandi tra documenti sono sempre link relativi.
