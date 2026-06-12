# Developer Rules — Plugin

> Regole **aggiuntive** (oltre a backend e frontend rules) per il codice dei plugin. Guida: [plugin-development/](../../plugin-development/README.md).

## Confini

- **PLG-1** — Tutto l'I/O di rete passa da `context.http`: mai librerie HTTP proprie, mai sessioni parallele. La politeness e il conteggio richieste sono del core, non negoziabili.
- **PLG-2** — DB: solo le proprie tabelle `plugin_<nome>_*`, create idempotentemente in `initialize()`. Mai leggere o scrivere tabelle del core o di altri plugin; il catalogo si alimenta **solo** via `update_catalog`.
- **PLG-3** — Niente accesso a filesystem fuori dalla propria cartella, niente variabili d'ambiente, niente stato globale di processo. Tutto ciò che serve arriva dal `PluginContext`.
- **PLG-4** — Log solo via `context.logger`; mai contenuti operativi degli utenti nei messaggi.

## Comportamento

- **PLG-5** — Mono-thread per contratto: nessun threading/asyncio interno verso il sito. Il lavoro lungo dev'essere interrompibile (il timeout di run del runner deve poterti fermare — e con l'esecuzione seriale un job appeso trattiene anche la coda).
- **PLG-6** — `run_test`/dry-run: **zero scritture**, di qualunque tipo. La CI lo verifica.
- **PLG-7** — `external_id`: stabile e univoco (SCR-R9); la strategia di derivazione è documentata nella doc del plugin in `implemented-plugins/`. Cambiarla è un breaking change per i dati degli utenti: si fa solo con una nota di migrazione.
- **PLG-8** — Idempotenza per-run: due run consecutive senza cambiamenti sul sito producono **zero** delta (è il check della checklist e il sintomo n.1 di `external_id` instabile).

## Qualità

- **PLG-9** — La suite di contratto del core ([checklist-and-testing](../../plugin-development/checklist-and-testing.md)) è obbligatoria e passa in CI; i test di parsing usano fixture salvate, mai il sito reale.
- **PLG-10** — Manifest completo (incl. `api_version` corrente e icona) e route documentate nello Swagger con tag `Plugin: <nome>`.
- **PLG-11** — Documentazione in `implemented-plugins/` prima del rilascio: overview + dettagli specifici + punti aperti. Un plugin non documentato non si abilita.
- **PLG-12** — Rispetto del sito osservato: nessun aggiramento di protezioni esplicite (captcha, blocchi), identificazione onesta nello user-agent di default, volumi di richieste minimi necessari. In caso di dubbio sulla liceità dell'osservazione di un sito, il dubbio vince.
