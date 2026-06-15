# Fase 12 — Rifinitura e 1.0

> Stato: ☐ da iniziare · Prerequisiti: tutte le precedenti · [Indice del flusso](README.md)

## Obiettivo

Chiudere il perimetro della 1.0: il secondo canale di notifica (che dimostra la bontà del contratto notifier), l'internazionalizzazione completa, la qualità trasversale (UX degli stati vuoti, CI piena, doc allineata).

## Risultato apprezzabile

**Release 1.0**: installazione pulita documentata in una pagina, due canali di notifica, app completa in italiano e inglese, CI che protegge tutto — il progetto è "finito" nel senso buono: da qui in poi si evolve per [future improvements](../future-improvements/README.md).

## MVP

### Backend

- [ ] **12.B1 — Discord: invio del digest** (~1h): webhook per-utente (config solo utente), embed per il digest ([discord](../implemented-plugins/notifiers/discord.md)). *Verifica: digest su un canale Discord reale; secondo canale attivo insieme all'email.*
- [ ] **12.B2 — Discord: summary e limiti** (~1h): embed del summary, gestione dei limiti di lunghezza degli embed. *Verifica: digest molto lungo → spezzato/troncato in modo leggibile.*
- [ ] **12.B3 — Discord: errori del webhook** (~1h): gestione 404 (webhook revocato) e 429 (rate limit) — chiude DSC-Q1/Q2. *Verifica: webhook revocato → esito failed con motivo chiaro all'utente.*
- [ ] **12.B4 — Test di contratto: scraper** (~1h): suite di contratto eseguita in CI per ogni scraper abilitato ([checklist-and-testing](../plugin-development/checklist-and-testing.md)). *Verifica: rompere il contratto di Dragon Store → CI rossa.*
- [ ] **12.B5 — Test di contratto: notifier** (~1h): idem per i notifier (Email, Discord). *Verifica: rompere un contratto notifier → CI rossa.*
- [ ] **12.B6 — Integrazione su Postgres effimero** (~1h): test d'integrazione in CI su Postgres effimero, coverage dei moduli critici ([ci](../infrastructure/ci.md)). *Verifica: suite verde in CI, rossa su regressione DB.*

### Frontend

- [ ] **12.F1 — Stati vuoti** (~1h): stati vuoti curati su tutte le pagine (FE-12). *Verifica: giro da utente nuovo senza momenti "e adesso?".*
- [ ] **12.F2 — Conferme distruttive + responsive** (~1h): conferme con conseguenze esplicite (FE-11), responsive di base. *Verifica: ogni azione distruttiva dichiara cosa cancella.*
- [ ] **12.F3 — Revisione dark/light** (~1h): passata su tutte le pagine nei due temi. *Verifica: nessun elemento illeggibile nei due temi.*

### Trasversali

- [ ] **12.T1 — Audit i18n: backend e notifier** (~1h): `en.json` completo nelle cartelle `i18n/` di core e plugin backend (notifier inclusi); nessuna stringa cablata né concatenata. *Verifica: notifiche complete in inglese, nessuna chiave mancante a runtime.*
- [ ] **12.T2 — Audit i18n: frontend** (~1h): `en.json` completo per core e plugin frontend (FE-13), fallback su `en` verificato. *Verifica: app completa in inglese.*
- [ ] **12.T3 — Doc allineata + audit README** (~1h): verifica documentazione vs implementato (DOC-8); audit del README come manuale operativo completo — install, update, backup/restore, tutti i comandi e script (INF-18). *Verifica: nessuna divergenza doc/codice nota; README autosufficiente.*
- [ ] **12.T4 — Release 1.0** (~1h): changelog, tag `1.0.0` → publish su GHCR + deploy kit in release ([ci](../infrastructure/ci.md), INF-17); prova di installazione pull-based da zero seguendo **solo il README**. *Verifica: macchina pulita con solo Docker + i due file del kit → sito su e manutenibile senza conoscenze esterne.*

## Definition of Done

- [ ] I due [use case fondanti](../1-business/use-cases.md) girano end-to-end su installazione pulita, su entrambi i canali (lingua: `en`, English-first).
- [ ] CI completa verde; checklist plugin passata da Dragon Store, Email e Discord.
- [ ] Tutte le checkbox di questo flusso spuntate: la 1.0 è chiusa.
- [ ] [docs-eng](../../docs-eng/) aggiornata in inglese con la sola parte implementata in questa fase (DOC-12).

## Riferimenti

[product-overview](../1-business/product-overview.md) · [developer-rules](../developer-rules/README.md)
