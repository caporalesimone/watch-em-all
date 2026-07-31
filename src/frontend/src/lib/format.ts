// Shared formatting helpers (phase 5 mini-SDK). Money is an exact Decimal string
// from the API; render it with the currency symbol (V1 only ever aggregates EUR).
export function money(value: string, currency: string | null): string {
	return !currency || currency === 'EUR' ? `€${value}` : `${value} ${currency}`;
}

// `priceDifference` used to live here, a second implementation of a rule the email already had
// in Python — the debt 9.F8 declared and could not pay, because the digest payload is stored and
// digests already written would not have carried the value. The 0.9.0 schema reset removed that
// obstacle, so the rule went to the core and the number now arrives already rendered (C19).

/** An ISO timestamp as `yyyy-mm-dd hh:mm:ss`, in the reader's own timezone. */
export function dateTime(iso: string): string {
	const d = new Date(iso);
	const p = (n: number) => String(n).padStart(2, '0');
	const date = `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
	return `${date} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}
