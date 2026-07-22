# Developer Rules — Documentation

> The wiki's rules: the 4 layers, what can go where, how it is maintained.

## The layer model (normative)

| Layer | Folder | May contain | May NOT contain |
|---|---|---|---|
| **1 — Business/UX** | `1-business/` | Only high-level **descriptive text**; simple tables; **up to 3 high-level Mermaid diagrams** across the whole layer (a declared exception, see below) | Code, pseudocode, table/endpoint names, detail diagrams (technical sequences, ER, internal flows) |
| **2 — Architecture** | `2-architecture/` | Text + **Mermaid diagrams**; tables | Code and pseudocode |
| **3 — Feature** | `3-features/` | Text + **Mermaid**; requirements with IDs; normative tables | Code and pseudocode |
| **4 — Capability** | `4-capabilities/` | Everything: **pseudocode**, Pydantic models, code references | — |

**Allowed deviations** (kept to the bare minimum and declared): **configuration** snippets in infrastructure documents; a minimal example where the text alone would be ambiguous. A deviation that becomes the norm is a document in the wrong layer.

**Diagram exception for Layer 1** (DOC-12 bis): **at most 3 high-level Mermaid diagrams across the whole Layer 1** are allowed — typically the **context diagram** (actors + system + external worlds), the end-to-end **value flow** and the **role map**. They must stay understandable to a stakeholder and **free of technical detail**: no table/endpoint names, pseudocode or internal sequences. Detail lives from Layer 2 down.

## Writing rules

- **DOC-1** — Every document declares at the top: **layer, audience**, and the links to the related documents (feature ↔ capability).
- **DOC-2** — Requirements have **module-prefixed IDs** (`CART-R3`, `CRON-R9`, `SCR-R7`): citable in commits, PRs and tests. IDs are not recycled: a removed requirement leaves its ID retired.
- **DOC-3** — A piece of information lives in **a single place** (the most appropriate layer); the other documents **link** it, they do not repeat it. The symptom to avoid: updating the same sentence in three files.
- **DOC-4** — Language: the reference documentation (`docs-ita/`) is in **Italian** (identifiers, technical terms and field names in English); the canonical wiki under construction (`docs/`) is in **English** (DOC-12). Links always relative.
- **DOC-5** — The generic plugin documents (layers 2-3-4 and plugin-development) **never cite real plugins** except as a pointer to `implemented-plugins/`. Everything site/channel-specific lives only there.
- **DOC-6** — **Simplifications** and **trade-offs** are declared in the document that adopts them ("declared choice: …"), never left implicit.
- **DOC-7** — Open points are tracked where they arise, with an ID (`DRG-Q1`), and closed by updating the document — not in scattered TODOs.

## Maintenance

- **DOC-8** — A PR that changes behaviour updates the involved documents **in the same PR** (process rule 3). The reviewer verifies it as part of the review.
- **DOC-9** — A new endpoint is born in [api/endpoints.md](../../api/endpoints.md) before its implementation; a new schema field is born in [database/schema.md](../../4-capabilities/database/schema.md).
- **DOC-10** — Diagrams are **Mermaid in the markdown** (versionable, diffable): no binary diagram images.
- **DOC-11** — Audience check before merge: does a stakeholder understand a layer 1? Is a layer 3 enough for a developer to estimate? Is a layer 4 enough to implement without asking?
- **DOC-13** — **`CHANGELOG.md` style** (decided 2026-06-20): every entry is **short** and readable by the user as a **story of what changed for them**. Two parts: (1) **bullet points** on **user-experience** changes — additions, removals and modifications **together**, short sentences, technical jargon to a minimum; (2) a **short prose paragraph** (`_Under the hood:_`) on the **architectural/technical** changes, with essential technical detail. No verbose `Added/Changed/Fixed` sections; the entry **must not be long**. Historical entries stay as they are; the rule applies from now on. The requirement **1 PR = 1 entry + bump** stays (INF-19).
- **DOC-12** — **English documentation in `docs/` (the designated canonical wiki)**: at the **close of each phase** of the [development flow](../../../docs-ita/development-flow/README.md), the `docs/` folder (repo root, English) is updated with the **English equivalent** of the `docs-ita/` reference documentation — **only and exclusively the part implemented** in that phase, across all the touched levels (layers 1-4 and cross-cutting sections), with the **same tree** as `docs-ita/`. The English documentation grows with the site: never describe in English what is not yet implemented, never leave behind what is. It is a Definition-of-Done item for every phase. **Transition**: `docs-ita/` stays the **source of truth** until `docs/` is complete (close of phase 12 / v1); at that point `docs-ita/` is retired and `docs/` remains the only wiki.
