// Shared formatting helpers (phase 5 mini-SDK). Money is an exact Decimal string
// from the API; render it with the currency symbol (V1 only ever aggregates EUR).
export function money(value: string, currency: string | null): string {
	return !currency || currency === 'EUR' ? `€${value}` : `${value} ${currency}`;
}

// `priceDifference` used to live here, a second implementation of a rule the email already had
// in Python — the debt 9.F8 declared and could not pay, because the digest payload is stored and
// digests already written would not have carried the value. The 0.9.0 schema reset removed that
// obstacle, so the rule went to the core and the number now arrives already rendered (C19).

/**
 * A duration counting **down**, so the seconds are always shown: `1h 05m`, `4m 03s`, `12s`.
 *
 * Two functions rather than one with a flag, because the two renderings are deliberate and the
 * names are what say so (C22). A countdown that dropped its seconds would look frozen for a
 * minute at a time; a configured interval that showed them would imply a precision it does not
 * have. Negative input is clamped: a countdown that has run out reads `0s`, never `-3s`.
 */
export function formatCountdown(totalSeconds: number): string {
	const s = Math.max(0, Math.floor(totalSeconds));
	const h = Math.floor(s / 3600);
	const m = Math.floor((s % 3600) / 60);
	const sec = s % 60;
	if (h > 0) return `${h}h ${String(m).padStart(2, '0')}m`;
	if (m > 0) return `${m}m ${String(sec).padStart(2, '0')}s`;
	return `${sec}s`;
}

/** A configured duration, read rather than watched: `1h 5m`, `5m`, `12s` — no seconds once
 * there are minutes, because nobody sets a politeness delay to the second. */
export function formatDuration(totalSeconds: number): string {
	const s = Math.max(0, Math.floor(totalSeconds));
	const h = Math.floor(s / 3600);
	const m = Math.floor((s % 3600) / 60);
	if (h > 0) return m > 0 ? `${h}h ${m}m` : `${h}h`;
	return m > 0 ? `${m}m` : `${s}s`;
}

/** An ISO timestamp as `yyyy-mm-dd hh:mm:ss`, in the reader's own timezone. */
export function dateTime(iso: string): string {
	const d = new Date(iso);
	const p = (n: number) => String(n).padStart(2, '0');
	const date = `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
	return `${date} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}
