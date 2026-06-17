# Future Improvements

> Miglioramenti **consapevolmente rimandati**: per ciascuno, il motivo del rinvio e il trigger che lo renderebbe attuale. Quando uno entra in lavorazione: si specifica nei layer giusti della wiki e si rimuove da qui.

## Indice per area

| Area | Documento |
|---|---|
| Piattaforma e infrastruttura | [platform.md](platform.md) |
| Notifiche e plugin | [plugins-and-notifications.md](plugins-and-notifications.md) |
| Osservabilità e dati | [observability-and-data.md](observability-and-data.md) |

## Criterio di rinvio

Il progetto è un hobby project per ≤5 utenti ([security posture](../2-architecture/security-posture.md)): un miglioramento si rimanda quando il suo costo (complessità, manutenzione) supera il valore a questa scala. Il rinvio è una decisione, non una dimenticanza: se manca il "perché no adesso", non è un future improvement — è un buco di specifica.

## Top 3 per probabilità di promozione

1. **Alembic per le migrazioni** — il primo breaking change di schema con dati reali lo renderà attuale ([observability-and-data](observability-and-data.md)).
2. **Notifier Telegram / Webhook generico** — canali a costo di sviluppo basso sul contratto esistente ([plugins-and-notifications](plugins-and-notifications.md)).
3. **Multi-timezone** — appena un utente vive in un fuso diverso dal server ([platform](platform.md)).
