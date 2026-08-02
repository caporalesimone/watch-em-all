// Shared auth state (FE-5). Actions do the I/O; the store only holds the result.
import { derived, writable, type Readable } from 'svelte/store';

import * as api from '$lib/api/client';
import { clearTokens, hasRefresh } from '$lib/auth/manager';

export interface AuthState {
	status: 'loading' | 'anon' | 'authed';
	user: api.Me | null;
}

export const auth = writable<AuthState>({ status: 'loading', user: null });

// Roles don't overlap (personas-and-roles.md): an admin governs and owns no catalog or carts,
// a user owns their own data. `isAdmin` picks which shell to draw.
export const isAdmin: Readable<boolean> = derived(
	auth,
	($auth) => ($auth.user?.role ?? 'user') === 'admin'
);

// The third level (9.B8): a user trusted with the tools that send unplanned traffic to a site
// — the manual scrape, and the Debug page of links to development tooling. Derived once here
// rather than spelled out in each component: the set is the backend's `_SUPER_ROLES`, and a
// copy per page is a copy that will disagree with it one page at a time.
const PRIVILEGED_ROLES = ['admin', 'super_user'];
export const isPrivileged: Readable<boolean> = derived(auth, ($auth) =>
	PRIVILEGED_ROLES.includes($auth.user?.role ?? 'user')
);

async function loadMe(): Promise<void> {
	try {
		// /api/me is reachable even while a password change is pending (it carries
		// the must_change_password flag); the guard routes on it.
		const user = await api.getMe();
		auth.set({ status: 'authed', user });
	} catch {
		clearTokens();
		auth.set({ status: 'anon', user: null });
	}
}

/** Restore a session on boot from the stored refresh token (FAUTH-R1). */
export function bootstrap(): Promise<void> {
	if (!hasRefresh()) {
		auth.set({ status: 'anon', user: null });
		return Promise.resolve();
	}
	return loadMe();
}

export async function signIn(username: string, password: string): Promise<void> {
	await api.login(username, password);
	await loadMe();
}

export async function signOut(): Promise<void> {
	await api.logout();
	auth.set({ status: 'anon', user: null });
}

/** Replace the cached profile after a PATCH /api/me, so the shell sees the new values. */
export function setUser(user: api.Me): void {
	auth.update((state) => ({ ...state, user }));
}

/** Used after a password change: the backend invalidated every token (AUTH-R5). */
export function forceAnon(): void {
	clearTokens();
	auth.set({ status: 'anon', user: null });
}
