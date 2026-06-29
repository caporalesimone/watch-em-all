// Shared formatting helpers (phase 5 mini-SDK). Money is an exact Decimal string
// from the API; render it with the currency symbol (V1 only ever aggregates EUR).
export function money(value: string, currency: string | null): string {
	return !currency || currency === 'EUR' ? `€${value}` : `${value} ${currency}`;
}
