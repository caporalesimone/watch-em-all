# Contratto — `Adjustment`

> **Layer 4 — Contratto** · Audience: developer, plugin developer · Pseudocodice ammesso. Feature: [carts](../../3-features/user/carts.md).

## Scopo

Una voce correttiva sul totale di un carrello **scraper-specific**, calcolata dal plugin secondo le regole del suo sito (sconti a soglia, spedizione, …) senza che il core ne conosca la logica.

## Modello

```python
from pydantic import BaseModel
from decimal import Decimal

class Adjustment(BaseModel):
    description: str    # leggibile, mostrato in card e notifiche
    amount: Decimal     # POSITIVO = sconto/risparmio · NEGATIVO = costo aggiuntivo
```

## Regole

- **ADJ-R1** — Il plugin restituisce zero o più voci da `get_adjustments(cart_total)`, dove `cart_total` è il **totale scontato corrente** dei prodotti attivi.
- **ADJ-R2** — Il core applica le voci senza interpretarle: `stima_finale = totale_scontato − Σ amount`.
- **ADJ-R3** — Solo carrelli **scraper-specific**: nei cross nessuna logica di sconto è comune a siti diversi, quindi nessun adjustment.
- **ADJ-R4** — La **soglia** del carrello si confronta con la **stima finale** (adjustments inclusi): vedi CART-R11.

## Esempio

```python
def get_adjustments(self, cart_total: Decimal) -> list[Adjustment]:
    # esempio generico: sconto a soglia + spedizione
    out = []
    if cart_total >= 100:
        out.append(Adjustment(description="Sconto soglia 100", amount=cart_total * Decimal("0.15")))
    out.append(Adjustment(description="Spese di spedizione", amount=Decimal("-7.00")))
    return out
```

Totale scontato 120 → stima finale = 120 − (18 − 7) = 109. Le voci compaiono in fondo alla card del carrello e nei payload delle notifiche.
