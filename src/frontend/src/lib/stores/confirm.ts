// Confirmation as a promise (10.T2).
//
// The four call sites this replaces all read `if (!confirm(...)) return;` — synchronous, one
// line, no state. A modal is neither, and rewriting each of them into open-a-flag / remember-
// the-pending-action / run-it-in-a-callback would have spread four copies of the same little
// state machine across four pages. So the state machine lives here, once, and a call site keeps
// its single line: `if (!(await confirmDialog({...}))) return;`
//
// The mechanics: the request goes into the store with its `resolve` attached, <ConfirmHost>
// renders it, and answering settles the promise. Only one can be pending — a second dialog
// stacked on the first is a design accident, so an in-flight request is refused rather than
// silently dropped, which would leave the first promise hanging for ever.

import { writable } from 'svelte/store';

export interface ConfirmRequest {
	title: string;
	message: string;
	/**
	 * The values interpolated into `message` that should stand out — a username, a date.
	 *
	 * Passed as **data, not markup**: the message stays a plain string and <ConfirmHost> does the
	 * emphasis by splitting on these substrings. The two alternatives were both worse. Markdown in
	 * the message would need a renderer here, and the app already renders Markdown on the server
	 * precisely so one set of rules cannot drift into two (9.F8). Bold tags in the translation
	 * would mean `{@html}` on a string that carries a username — untrusted text into the DOM, to
	 * make a word heavier.
	 *
	 * Every occurrence is emphasised, so a message that names the account twice reads the same
	 * both times.
	 */
	highlight?: string[];
	/** Label of the affirmative button; say what will happen ("Delete", "Send"), not "OK". */
	confirmLabel: string;
	/** Destructive or irreversible: the button goes red. */
	danger?: boolean;
}

type Pending = ConfirmRequest & { resolve: (answer: boolean) => void };

export const pendingConfirm = writable<Pending | null>(null);

let inFlight = false;

export function confirmDialog(request: ConfirmRequest): Promise<boolean> {
	if (inFlight) return Promise.resolve(false);
	inFlight = true;
	return new Promise<boolean>((resolve) => {
		pendingConfirm.set({
			...request,
			resolve: (answer) => {
				inFlight = false;
				pendingConfirm.set(null);
				resolve(answer);
			}
		});
	});
}
