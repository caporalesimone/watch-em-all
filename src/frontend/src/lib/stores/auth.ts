// Shared auth state (FE-5). Actions do the I/O; the store only holds the result.
import { writable } from 'svelte/store';

import * as api from '$lib/api/client';
import { clearTokens, hasRefresh } from '$lib/auth/manager';

export interface AuthState {
	status: 'loading' | 'anon' | 'authed';
	user: api.Me | null;
}

export const auth = writable<AuthState>({ status: 'loading', user: null });

async function loadMe(fallbackUsername?: string): Promise<void> {
	try {
		const user = await api.getMe();
		auth.set({ status: 'authed', user });
	} catch (err) {
		// The forced-change gate (AUTH-R7) 403s /api/me; treat it as authenticated
		// but pending a password change so the guard routes to /change-password.
		if (err instanceof api.ApiErr && err.status === 403 && err.code === 'must_change_password') {
			auth.set({
				status: 'authed',
				user: {
					id: 0,
					username: fallbackUsername ?? '',
					role: '',
					locale: 'en',
					must_change_password: true
				}
			});
			return;
		}
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
	await loadMe(username);
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
