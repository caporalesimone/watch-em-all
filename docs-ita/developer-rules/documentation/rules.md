# Developer Rules — Documentazione

> Le regole della wiki: i 4 layer, cosa può stare dove, come si mantiene.

## Il modello a layer (normativo)

| Layer | Cartella | Può contenere | NON può contenere |
|---|---|---|---|
| **1 — Business/UX** | `1-business/` | Solo **testo descrittivo** ad alto livello; tabelle semplici; **fino a 3 diagrammi Mermaid di alto livello** in tutto il layer (eccezione dichiarata, vedi sotto) | Codice, pseudocodice, nomi di tabelle/endpoint, diagrammi di dettaglio (sequenze tecniche, ER, flussi interni) |
| **2 — Architettura** | `2-architecture/` | Testo + **diagrammi Mermaid**; tabelle | Codice e pseudocodice |
| **3 — Feature** | `3-features/` | Testo + **Mermaid**; requisiti con ID; tabelle normative | Codice e pseudocodice |
| **4 — Capability** | `4-capabilities/` | Tutto: **pseudocodice**, modelli Pydantic, riferimenti al codice | — |

**Deroghe ammesse** (al minimo indispensabile e dichiarate): snippet di **configurazione** nei documenti di infrastruttura; un esempio minimo dove il testo da solo sarebbe ambiguo. Una deroga che diventa la norma è un documento nel layer sbagliato.

**Eccezione diagrammi per il Layer 1** (DOC-12 bis): sono ammessi **al massimo 3 diagrammi Mermaid di alto livello in tutto il Layer 1** — tipicamente il **diagramma di contesto** (attori + sistema + mondi esterni), il **flusso di valore** end-to-end e la **mappa dei ruoli**. Devono restare comprensibili a uno stakeholder e **privi di dettaglio tecnico**: niente nomi di tabella/endpoint, pseudocodice o sequenze interne. Il dettaglio vive dal Layer 2 in giù.

## Regole di scrittura

- **DOC-1** — Ogni documento dichiara in testa: **layer, audience**, e i link ai documenti correlati (feature ↔ capability).
- **DOC-2** — I requisiti hanno **ID prefissati per modulo** (`CART-R3`, `CRON-R9`, `SCR-R7`): citabili in commit, PR e test. Gli ID non si riciclano: un requisito rimosso lascia il suo ID ritirato.
- **DOC-3** — Un'informazione vive in **un solo posto** (il layer più appropriato); gli altri documenti la **linkano**, non la ripetono. Il sintomo da evitare: aggiornare la stessa frase in tre file.
- **DOC-4** — Lingua: la documentazione di riferimento (`docs-ita/`) è in **italiano** (identificatori, termini tecnici e nomi di campo in inglese); la wiki canonica in costruzione (`docs/`) è in **inglese** (DOC-12). Link sempre relativi.
- **DOC-5** — I documenti generici dei plugin (layer 2-3-4 e plugin-development) **non citano mai plugin reali** se non come rimando a `implemented-plugins/`. Tutto ciò che è specifico di un sito/canale vive solo lì.
- **DOC-6** — Le **semplificazioni** e i **trade-off** si dichiarano nel documento che li adotta ("scelta dichiarata: …"), mai lasciati impliciti.
- **DOC-7** — I punti aperti si tracciano dove nascono, con ID (`DRG-Q1`), e si chiudono aggiornando il documento — non in TODO sparsi.

## Manutenzione

- **DOC-8** — Una PR che cambia comportamento aggiorna i documenti coinvolti **nella stessa PR** (regola di processo n.3). Il reviewer la verifica come parte della review.
- **DOC-9** — Un endpoint nuovo nasce in [api/endpoints.md](../../api/endpoints.md) prima dell'implementazione; un campo di schema nuovo nasce in [database/schema.md](../../4-capabilities/database/schema.md).
- **DOC-10** — I diagrammi sono **Mermaid nel markdown** (versionabili, diffabili): niente immagini binarie di diagrammi.
- **DOC-11** — Audience check prima del merge: un layer 1 lo capisce uno stakeholder? Un layer 3 basta a un developer per stimare? Un layer 4 basta per implementare senza chiedere?
- **DOC-12** — **Documentazione inglese in `docs/` (wiki canonica designata)**: alla **chiusura di ogni fase** del [development flow](../../development-flow/README.md), la cartella `docs/` (root del repo, inglese) si aggiorna con l'**equivalente inglese** della documentazione di riferimento `docs-ita/` — **solo ed esclusivamente la parte implementata** in quella fase, su tutti i livelli toccati (layer 1-4 e sezioni trasversali), con la **stessa alberatura** di `docs-ita/`. La documentazione inglese cresce con il sito: mai descrivere in inglese ciò che non è ancora implementato, mai lasciare indietro ciò che lo è. È un item della Definition of Done di ogni fase. **Transizione**: `docs-ita/` resta la **source of truth** finché `docs/` non è completa (chiusura fase 12 / v1); a quel punto `docs-ita/` viene ritirata e `docs/` resta l'unica wiki.
