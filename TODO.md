# TODO

Running list of issues / polish noted by Simone, to address in a future pass.
New items get appended over time. **Done items are removed from here** — the record of what was
decided and why lives in the commits (`git log`), in the CHANGELOG entry of the version that
shipped it, and in the phase document.


## bug della fase 10 da sistemare

- le notifiche lette nella ui devono leggermente grigiarsi. restano in bianco evidente come ora solo quelle non lette.

- forziamo come username la mail dell'utente. Al momento resta l'admin l unico creatore
ma deve inserire una mail valida come username.
Alla creazione, anziché inserire lui la password viene mandata una mail con la password generata da usare per il primo login. Dopo il primo login l utente deve cambiare la password.
A questo punto nella ui admin viene tolta la possibilitá di inserire la password. E'tutto gestito dal sistema.
Resta valido per l admin il cambio password se necessario con la stessa logica. 
Premendolo viene invalidata la password attuale e anche la sessione. Viene sloggato l utente e viene mandata una mail con la nuova password generata da usare per il primo login. Dopo il primo login l utente deve cambiare la password.
la validazione che l username sia una mail va fattia sia lato frontend che backend. Il backend deve essere l'ultima linea di difesa. 

## debug

- il valore di cache nella pagina admin del plugin é da verificare. 
prima segnalava 2 o 3 ma cé solo una categoria attiva.
quanto dovrebbe essere la cache in questo caso?

- con docker ps pgweb non mostra lo stato di healthy. se costa poco aggiungerlo
sosedoff/pgweb:0.16.2   "/usr/bin/pgweb --bi…"   4 hours ago   Up About an hour          




## Off topic

- **Two Claude Code skills: start-of-work and end-of-work.** Create a `/start-work` skill that opens a
  phase/PR (branch, dated status header, empty CHANGELOG placeholder, version bookkeeping) and an
  `/end-work` skill that closes it (finalize the CHANGELOG entry, tick the checklist, the tag +
  GitHub-release steps, image/version sanity check). They'd encode the repeatable versioning/tagging
  ritual — one tag per phase, no `v` prefix, `WEA_VERSION` in `.env`, version baked from `git describe`
  — so it isn't re-derived by hand each time. See [`docs/env-variables.md`](docs/env-variables.md) and
  the version notes in [ci](docs-ita/infrastructure/ci.md) for what the skills should automate.
