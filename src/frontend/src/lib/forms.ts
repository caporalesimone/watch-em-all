// Has this form been touched? (10.F23)
//
// Every Save button in the app now answers the same question before it lights up: is what is on
// screen different from what was loaded, or last saved? A Save that is always clickable invites
// a click that writes the values already stored -- harmless in itself, but it teaches that the
// button means nothing, and next to a switch that *does* act immediately (the notifier
// kill-switch) that is exactly the wrong lesson.
//
// The comparison is a structural one rather than a field-by-field diff, because the alternative
// is one comparison written per page, each free to forget a field the day one is added.

/**
 * Whether an editable copy still matches its baseline.
 *
 * `JSON.stringify` and not a deep-equal helper: the things compared here are what an API returned
 * and what a form did to it -- plain objects of strings, numbers and booleans, no dates, no
 * classes, no cycles. Key order is stable because the baseline is always a snapshot of the same
 * shape the editable copy came from, and object spread preserves it.
 *
 * Works on Svelte 5 `$state` proxies without unwrapping them.
 */
export function changed(current: unknown, baseline: unknown): boolean {
	return JSON.stringify(current) !== JSON.stringify(baseline);
}

/** A detached copy to compare against later. */
export function snapshot<T>(value: T): T {
	return JSON.parse(JSON.stringify(value)) as T;
}
