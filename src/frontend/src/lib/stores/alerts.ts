// Unread-alerts badge state (6.F4). A tiny shared store the Sidebar subscribes to and
// that the alert history refreshes after marking a notification read, so the pill in
// the nav stays in sync without a full reload.
import { writable } from 'svelte/store';

import { getUnreadCount } from '$lib/api/client';

/** Number of unread alerts for the current user; 0 hides the sidebar badge. */
export const unreadCount = writable<number>(0);

/** Re-read the unread count from the backend; leaves the last value on error. */
export async function refreshUnread(): Promise<void> {
	try {
		unreadCount.set(await getUnreadCount());
	} catch {
		/* keep the last known count — a transient failure must not clear the badge */
	}
}

/** Clear the count on sign-out. */
export function resetUnread(): void {
	unreadCount.set(0);
}
