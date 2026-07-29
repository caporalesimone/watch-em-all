// Shared formatting helpers (phase 5 mini-SDK). Money is an exact Decimal string
// from the API; render it with the currency symbol (V1 only ever aggregates EUR).
export function money(value: string, currency: string | null): string {
	return !currency || currency === 'EUR' ? `€${value}` : `${value} ${currency}`;
}

/**
 * The signed percentage change between two observations of a price — the *Difference* the
 * digest reports, in the same form the email renders (9.X10/9.F8).
 *
 * `null` when there is nothing to compare against, which the page shows as an em dash.
 * Deliberately **not** the product's sale discount: that compares against the list price,
 * a different quantity, and printing it beside a `was → now` pair showed `-0%` on a product
 * whose price had just risen. One decimal, dropped when it is zero, so a real sub-1% change
 * never collapses into a misleading `0%`.
 */
export function priceDifference(previous: string | null, current: string): string | null {
	if (previous === null) return null;
	const before = Number(previous);
	const after = Number(current);
	if (!Number.isFinite(before) || !Number.isFinite(after) || before === 0) return null;
	const pct = ((after - before) / before) * 100;
	const rounded = Math.round(pct * 10) / 10;
	if (rounded === 0) return '0%'; // also catches -0, which would print as "-0%"
	const text = Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
	return rounded > 0 ? `+${text}%` : `${text}%`;
}

/** An ISO timestamp as `yyyy-mm-dd hh:mm:ss`, in the reader's own timezone. */
export function dateTime(iso: string): string {
	const d = new Date(iso);
	const p = (n: number) => String(n).padStart(2, '0');
	const date = `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
	return `${date} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}
