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
7. **Docs inglesi a fine fase**: alla chiusura di ogni fase del [development flow](../development-flow/README.md), la documentazione inglese in `docs/` (la wiki canonica designata) si aggiorna con l'equivalente della sola parte implementata (DOC-12) — cresce insieme al sito; `docs-ita/` resta il riferimento finché `docs/` non è completa (v1), poi va in pensione.
8. **Zero-install**: niente software di sviluppo sull'host, di dev o di hosting — solo Docker; si sviluppa nel [dev container](../infrastructure/dev-container.md) (INF-15).
9. **Ogni PR = una versione; le release le tagga l'owner a mano**: ogni PR porta un **bump di versione** (SemVer) e una voce in **`CHANGELOG.md`**; senza, non è mergiabile (INF-19). I tag **non** sono per-PR: il tag `x.y.z` (SemVer puro, senza prefisso `v`) lo crea **l'owner a mano** quando vuole una release ([ci](../infrastructure/ci.md#tag-e-release-manuali)) e il push del tag pubblica immagini e release; le versioni intermedie vivono solo nel CHANGELOG.
10. **Merge dell'owner**: l'autore della modifica apre la PR (branch + commit + PR); **review e merge su `main` sono dell'owner**. Durante una PR è disponibile un'immagine dev `dev-<branch>` per provare prima del merge.
