# Main use cases

> **Layer 1 — Business** · Audience: everyone · Descriptive text only.
>
> English mirror of the Italian reference [`docs-ita/1-business/use-cases.md`](../../docs-ita/1-business/use-cases.md), limited to what is implemented (DOC-12). The two founding scenarios (UC-1, UC-2) are supported end to end today except for their final beat — the **automatic notification**, which arrives in a later phase; where it appears below it is called out as such. The purely spec-ahead contour case (the periodic **summary report**) stays in the Italian document.

The two founding use cases of the product. Every design choice must trace back to one of them.

## UC-1 — The bulk purchase at the best possible saving

> *"I keep an eye on a set of products and buy them in one go the moment the overall saving satisfies me."*

Marco collects board games. On his favourite online shop he has picked out twelve titles he wants to buy, but he is in no hurry: he knows prices fluctuate and that, buying everything together, he would pass the spending threshold above which the shop applies an extra discount and free shipping.

With Watch 'Em All, Marco:

1. configures the shop's scraper, indicating the products (or categories) to observe;
2. creates a "Games wishlist" cart and puts the twelve titles in it;
3. sets the threshold: *"tell me when the total drops below €300"* (which he can enter as a % — a UI aid — while the shop-aware € value is what is stored).

From then on the system observes for him. It computes the cart's total — including the shop's threshold discounts and the shipping it would apply (the so-called *adjustments*) — and shows when that total drops below the threshold: the moment to buy everything in one go. *(The automatic notification that announces it arrives in a later phase; today the cart displays the reached state.)*

**What this use case demands of the system**: carts with totals computed the way the shop would compute them (threshold discounts, shipping — the *adjustments*), an absolute € threshold (with a % entry aid), and — later — the aggregated notification.

## UC-2 — The same product on several sites

> *"I monitor a certain product on several different sites and I want to know when it goes on offer on any one of them."*

Giulia wants a specific camera, sold by three different online shops. She does not care whom she buys it from: she cares about the first one to discount it.

With Watch 'Em All, Giulia:

1. configures the three scrapers (one per shop) on the same product;
2. creates a **cross-store cart** "Camera" and adds the product **three times: once per site**;
3. watches each row's price and availability in the cart.

Inside the cart Giulia sees **clearly which site each row comes from**: the provenance (shop name and icon) is always shown next to every product, both in the carts pages and in the cart detail. Without this information a cross cart would be unreadable — three identical rows with no way to know who is discounting. *(The per-product alerts "on offer" / "back in stock", and their notification, arrive in a later phase.)*

**What this use case demands of the system**: carts that accept products from different scrapers, the "same" product present several times (once per site), **provenance always explicit** on every row, and — later — per-product alerts inside the cart.

## Contour use cases

- **Availability surveillance**: products that come and go from stock; the catalog and cart totals track availability today (unavailable products stay in place, excluded from the totals until they return), and the "back in stock" alert — later — will matter as much as a discount one.
- **Administration**: the admin decides how many times a day the scrapers run, and intervenes if something breaks. See [admin-experience.md](admin-experience.md).
