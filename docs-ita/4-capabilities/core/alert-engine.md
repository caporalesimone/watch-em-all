# Alert Engine — parti pianificate (spec-ahead)

> **Layer 4 — Capability** · Audience: developer · Pseudocodice ammesso. Il **motore alert implementato** (baseline seed/advance/delete, diff prodotti + eventi carrello, aggregazione in un solo `AlertEvent` scritto in `alert_log`) è documentato in inglese: [alert-engine](../../../docs/4-capabilities/core/alert-engine.md). Questa pagina raccoglie solo le parti **non ancora implementate**: la consegna ai canali (fase 7) e il tag minimo storico (fase 11). Feature: [alerts-and-notifications](../../3-features/user/alerts-and-notifications.md) · Architettura: [notification-architecture](../../2-architecture/notification-architecture.md) · Contratto: [alert-event](../contracts/alert-event.md).

## Minimo storico (fase 11)

Nel diff prodotti, oltre ai tag già implementati, un ulteriore ribasso che porta il prezzo al minimo mai registrato produce il tag `PRODUCT_ALL_TIME_LOW` (in aggiunta a `PRODUCT_ON_SALE`). Dipende dalle analitiche di prezzo (ANLZ-R4, [price-analytics](price-analytics.md)) e si innesta nel ciclo prodotti della run:

```
if m.price_current < prev.price_current and analytics.is_all_time_low(m):
    tags.append(PRODUCT_ALL_TIME_LOW)         # ribasso al minimo mai registrato (ANLZ-R4)
```

| Caso | Comportamento |
|---|---|
| Ribasso che tocca il minimo mai registrato | Tag ALL_TIME_LOW (in aggiunta a ON_SALE); non si ripete finché il prezzo resta fermo |

## Consegna ai canali — ASINCRONA (fase 7)

L'`AlertEvent` è scritto nello storico **sempre e subito**, a fine scrape (fase 6). La **consegna sui canali NON è inline** nel run di scrape: a 50–100 utenti un singolo scrape può notificarne molti, e fare gli invii SMTP dentro il worker (mono-thread, seriale) lo bloccherebbe / ne mangerebbe il timeout (ragionamento 2026-07-23, vedi il reminder in [phase-07-email-notifier](../../development-flow/phase-07-email-notifier.md)). Quindi:

1. **All'atto della scrittura del digest** (fase 6, già fatto) si creano le righe **`alert_delivery` in stato `pending`** — una per canale attivo dell'utente — oppure una riga `skipped_no_notifier` se non ce ne sono. (Questo pezzo si aggiunge in 7.B2.)
2. Un **passo separato del worker** drena le `pending`: prova l'invio (`ch.plugin.send(...)`), poi aggiorna l'esito a `delivered` / `failed` con retry/backoff.

```
# worker: drena la coda di consegna
def drain_deliveries():
    for d in alert_delivery where d.status == "pending":
        cfg = merge_config(d.plugin, d.user)          # chiavi utente filtrate sullo schema utente
        try:
            d.plugin.send(load(d.alert_id), cfg, locale_of(d.user))
            d.status = "delivered"
        except Exception as e:
            d.status = "failed"; d.error = str(e)     # niente retry infinito: il prossimo digest porta il nuovo stato
            log_warning("alert", f"consegna fallita {d.plugin} per {d.user}")
```

Proprietà: lo storico (`alert_log`) è la **fonte primaria**, scritto sempre a prescindere dalla consegna; un canale fallito non blocca gli altri (esiti indipendenti per canale in `alert_delivery`); **best-effort** (nessun retry differito all'infinito — il prossimo digest porta il nuovo stato). Riusa la tabella `alert_delivery` già a piano: niente broker/coda pesante né dead-letter.

| Caso | Comportamento |
|---|---|
| Tutti i canali falliti | Digest nello storico con esiti `failed`; nessun retry differito (il prossimo digest porta il nuovo stato) |
