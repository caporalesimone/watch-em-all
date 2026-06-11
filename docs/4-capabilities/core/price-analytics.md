# Price Analytics

> **Layer 4 — Capability** · Audience: developer · Pseudocodice ammesso. Feature: [price-analytics](../../3-features/user/price-analytics.md) · Dati: [price-history](price-history.md).

## Scopo

Calcolare statistiche e indicatori di convenienza **on-demand** da `price_history`. Nessuna tabella nuova, nessun job: a questa scala (storici di decine/centinaia di entry per prodotto) il calcolo al volo è immediato e sempre fresco.

## Statistiche di prodotto

```
MIN_HISTORY_DAYS, MIN_HISTORY_ENTRIES = 30, 3

def product_stats(product_id) -> ProductStats | InsufficientHistory:
    entries = history(product_id)                       # ordinate per recorded_at
    if span_days(entries) < MIN_HISTORY_DAYS or len(entries) < MIN_HISTORY_ENTRIES:
        return InsufficientHistory()                    # ANLZ-R6: mai numeri fuorvianti

    current = entries[-1]
    return ProductStats(
        min_price       = min(e.price_current for e in entries),
        min_price_date  = argmin(entries).recorded_at,
        max_price       = max(e.price_current for e in entries),
        max_price_date  = argmax(entries).recorded_at,
        avg_30d         = stepwise_avg(entries, days=30),    # media PESATA sul tempo
        avg_90d         = stepwise_avg(entries, days=90),
        pct_time_on_sale= stepwise_pct(entries, lambda e: e.discount_pct > 0),
        changes_count   = len(entries),
        is_all_time_low = current.price_current <= min(e.price_current for e in entries),
    )
```

Nota di correttezza: lo storico è **a gradini** (entry solo al cambio): media e percentuali si pesano sulla **durata** di ogni gradino, non sul conteggio delle entry (`stepwise_avg`/`stepwise_pct`), altrimenti un prodotto volatile distorcerebbe i numeri.

## `is_all_time_low` per l'Alert Engine

Usato dal [diff dell'Alert Engine](alert-engine.md) per il tag `PRODUCT_ALL_TIME_LOW`:

```
def is_all_time_low(product) -> bool:
    stats = product_stats(product.id)
    return (not isinstance(stats, InsufficientHistory)) and stats.is_all_time_low
```

Il tag scatta solo se il prezzo è **appena sceso** rispetto alla baseline **e** è il minimo mai registrato: il diff evita la ripetizione a ogni run finché il prezzo resta fermo al minimo.

## Indicatore di convenienza (euristica trasparente)

```
def convenience(product) -> ConvenienceVerdict | None:
    s = product_stats(product.id)
    if isinstance(s, InsufficientHistory): return None
    cur = current_price(product)

    signals = {
        "at_all_time_low":  s.is_all_time_low,
        "near_minimum":     cur <= s.min_price * Decimal("1.05"),   # entro il 5% dal minimo
        "below_avg_30d":    cur < s.avg_30d,
        "discount_vs_avg":  current_discount(product) > avg_discount(s),
    }
    score = sum(signals.values())
    label = "great" if score >= 3 else "average" if score == 2 else "wait"
    return ConvenienceVerdict(label=label, signals=signals, stats=s)
    # ANLZ-R5: il client mostra SEMPRE i segnali e i numeri, mai la sola etichetta
```

Soglie e pesi sono costanti dichiarate (non config utente): semplicità prima della personalizzazione.

## API

| Endpoint | Risposta |
|---|---|
| `GET /api/products/{id}/stats` | `ProductStats` + `ConvenienceVerdict` (o `insufficient_history`) |
| `GET /api/catalog` | ogni riga include il flag `is_all_time_low` (per il badge, calcolato in batch sulla pagina richiesta) |

Performance: il calcolo per pagina di catalogo (≤50 prodotti) è una manciata di query indicizzate (`(product_id, recorded_at)`): nessuna cache necessaria a questa scala — se mai servisse, è un [future improvement](../../future-improvements/observability-and-data.md) naturale.
