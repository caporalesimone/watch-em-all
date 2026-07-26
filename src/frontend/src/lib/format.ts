// Shared formatting helpers (phase 5 mini-SDK). Money is an exact Decimal string
// from the API; render it with the currency symbol (V1 only ever aggregates EUR).
export function money(value: string, currency: string | null): string {
	return !currency || currency === 'EUR' ? `€${value}` : `${value} ${currency}`;
}

/** An ISO timestamp as `yyyy-mm-dd hh:mm:ss`, in the reader's own timezone. */
export function dateTime(iso: string): string {
	const d = new Date(iso);
	const p = (n: number) => String(n).padStart(2, '0');
	const date = `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
	return `${date} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}
