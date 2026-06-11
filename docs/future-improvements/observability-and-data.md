# Future Improvements — Osservabilità e dati

> Formato: cosa · perché rimandato · trigger di promozione.

## Alembic (migrazioni di schema versionate)

Oggi: schema additivo idempotente + script SQL manuali per i breaking change (DB-R4). **Miglioria**: Alembic con history versionata — con SQLAlchemy è quasi gratis e protegge `price_history` (non ricostruibile). È il future improvement con il miglior rapporto valore/costo. **Trigger**: il primo breaking change di schema con dati reali in produzione.

## Log di sistema in push (WebSocket/SSE)

Oggi la pagina admin fa polling incrementale con cursore: semplice e sufficiente. **Miglioria**: push real-time. **Rimandato perché**: il polling a pochi secondi è indistinguibile per un admin umano. **Trigger**: mai, probabilmente — candidato alla rimozione.

## Metriche e dashboard (Prometheus/Grafana)

Oggi: statistiche delle run nel DB + pagina admin. **Miglioria**: export metriche standard. **Rimandato perché**: una seconda infrastruttura di monitoring per 4 container è sproporzionata; la pagina admin copre le domande reali. **Trigger**: l'installazione entra in una home-lab con stack di monitoring già esistente.

## Storico della composizione dei carrelli

Il grafico di carrello proietta la composizione **corrente** sul passato (HIST-R4, semplificazione dichiarata). **Miglioria**: `added_at`/`removed_at` su `cart_members` e ricostruzione fedele. **Rimandato perché**: complica modello e query per un raffinamento percettivo. **Trigger**: richiesta reale di analisi storica dei carrelli.

## Monitoraggio del carico per-utente (quote)

Il dettaglio per-utente delle run esiste già (`scrape_user_log`); manca un sistema di **quote** (max input per utente, max prodotti). **Rimandato perché**: con ≤5 utenti fidati si risolve a voce. **Trigger**: un utente che mette in difficoltà le run ripetutamente.

> ℹ️ *Promosse a feature* (non più future improvements): **analisi dei prezzi** → [price-analytics](../3-features/user/price-analytics.md) · **esportazione dati utente** → [data-export](../3-features/user/data-export.md).
