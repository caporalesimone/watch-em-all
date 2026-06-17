// Shared auth state (FE-5). Actions do the I/O; the store only holds the result.
import { writable } from 'svelte/store';

import * as api from '$lib/api/client';
import { clearTokens, hasRefresh } from '$lib/auth/manager';

export interface AuthState {
	status: 'loading' | 'anon' | 'authed';
	user: api.Me | null;
}

export const auth = writable<AuthState>({ status: 'loading', user: null });

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

/** Used after a password change: the backend invalidated every token (AUTH-R5). */
export function forceAnon(): void {
	clearTokens();
	auth.set({ status: 'anon', user: null });
}
