# Fase 12 — Rifinitura e v1.0

> Stato: ☐ da iniziare · Prerequisiti: tutte le precedenti · [Indice del flusso](README.md)

## Obiettivo

Chiudere il perimetro della v1: il secondo canale di notifica (che dimostra la bontà del contratto notifier), l'internazionalizzazione completa, la qualità trasversale (UX degli stati vuoti, CI piena, doc allineata).

## Risultato apprezzabile

**Release 1.0**: installazione pulita documentata in una pagina, due canali di notifica, app completa in italiano e inglese, CI che protegge tutto — il progetto è "finito" nel senso buono: da qui in poi si evolve per [future improvements](../future-improvements/README.md).

## MVP

### Backend

- [ ] **12.B1 — Notifier Discord** (~4h): webhook per-utente (config solo utente), embed per digest e summary con limiti gestiti, gestione 404/429 ([discord](../implemented-plugins/notifiers/discord.md), chiude DSC-Q1/Q2). *Verifica: digest su un canale Discord reale; secondo canale attivo insieme all'email.*
- [ ] **12.B2 — CI piena + test di contratto** (~4h): suite di contratto per scraper e notifier in CI per ogni plugin abilitato, test d'integrazione su Postgres effimero, coverage dei moduli critici ([checklist-and-testing](../plugin-development/checklist-and-testing.md), [ci](../infrastructure/ci.md)). *Verifica: rompere un contratto di plugin → CI rossa.*

### Frontend

- [ ] **12.F1 — UX polish** (~3h): stati vuoti curati (FE-12), conferme distruttive con conseguenze (FE-11), responsive di base, revisione dark/light su tutte le pagine. *Verifica: giro completo dell'app da utente nuovo senza momenti "e adesso?".*

### Trasversali

- [ ] **12.T1 — Audit i18n English-first** (~3h): audit delle stringhe — `en.json` completo nelle cartelle `i18n/` di core e plugin (frontend e backend dei notifier); nessuna stringa cablata né concatenata (FE-13); fallback su `en` verificato. *Verifica: app e notifiche complete in inglese; nessuna chiave mancante a runtime.*
- [ ] **12.T2 — Doc allineata + release** (~2h): verifica documentazione vs implementato (DOC-8), audit del README come manuale operativo completo — install, update, backup/restore, tutti i comandi e script (INF-18), changelog, tag `v1.0` → publish su GHCR + deploy kit in release ([ci](../infrastructure/ci.md), INF-17); prova di installazione pull-based da zero seguendo **solo il README**. *Verifica: macchina pulita con solo Docker + i due file del kit → sito su e manutenibile senza conoscenze esterne.*

## Definition of Done

- [ ] I due [use case fondanti](../1-business/use-cases.md) girano end-to-end su installazione pulita, su entrambi i canali (lingua: `en`, English-first).
- [ ] CI completa verde; checklist plugin passata da Dragon Store, Email e Discord.
- [ ] Tutte le checkbox di questo flusso spuntate: la v1 è chiusa.
- [ ] [docs-eng](../../docs-eng/) aggiornata in inglese con la sola parte implementata in questa fase (DOC-12).

## Riferimenti

[product-overview](../1-business/product-overview.md) · [developer-rules](../developer-rules/README.md)
