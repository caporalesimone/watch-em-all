# Developer Rules

> Regole vincolanti per chi contribuisce al progetto. La CI fa rispettare quelle automatizzabili ([ci](../infrastructure/ci.md)); le altre si fanno rispettare in review.

## Sezioni

| Sezione | Contenuto |
|---|---|
| [backend/rules.md](backend/rules.md) | Python: stile, tipi, Pydantic, errori, logging, test |
| [frontend/rules.md](frontend/rules.md) | Svelte/TypeScript: stile, store, API layer, design system, i18n |
| [infrastructure/rules.md](infrastructure/rules.md) | Docker, configurazione, segreti, dipendenze |
| [plugins/rules.md](plugins/rules.md) | Regole aggiuntive per il codice dei plugin |
| [documentation/rules.md](documentation/rules.md) | Le regole dei 4 layer e la manutenzione della wiki |

## Regole di processo (valgono per tutti)

1. **`main` sempre verde**: nessun merge con CI rossa. Lavoro su branch, merge via PR anche da soli (la PR è il posto del diff e della CI).
2. **Commit**: messaggi imperativi e specifici; un cambiamento logico per commit. Citare gli ID dei requisiti quando si implementano (`feat: catch-up cross-midnight (CRON-R2)`).
3. **Requisiti prima del codice**: una feature nuova si scrive prima nei documenti (layer giusto, ID requisito), poi nel codice. Se il codice contraddice la wiki, uno dei due è rotto: sistemarli insieme nella stessa PR.
4. **API-first**: un endpoint nuovo nasce in [api/endpoints.md](../api/endpoints.md) prima dell'implementazione.
5. **Niente TODO anonimi**: ogni `TODO` nel codice ha un riferimento (issue o punto aperto documentato).
6. **Le semplificazioni si dichiarano**: questo è un hobby project e le leggerezze sono ammesse ([security posture](../2-architecture/security-posture.md)) — ma sempre per iscritto, mai implicite.
