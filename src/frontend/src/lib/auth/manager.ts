// Auth Manager (auth-manager.md): the only module that knows about tokens.
// access in memory, refresh in localStorage (FAUTH-R1); automatic Bearer header
// (FAUTH-R2); single-flight refresh (FAUTH-R4) with one retry on 401 (FAUTH-R3)
// and a proactive refresh near expiry (FAUTH-R5). UI/domain never see a token.
import { browser } from '$app/environment';

const REFRESH_KEY = 'wea_refresh';
const PROACTIVE_MS = 60_000;

interface TokenPair {
	access_token: string;
	refresh_token: string;
	expires_at: string;
}

let accessToken: string | null = null;
let refreshToken: string | null = browser ? localStorage.getItem(REFRESH_KEY) : null;
let expiresAt = 0;
let refreshing: Promise<boolean> | null = null;

export function hasRefresh(): boolean {
	return refreshToken !== null;
}

export function setTokens(pair: TokenPair): void {
	accessToken = pair.access_token;
	refreshToken = pair.refresh_token;
	expiresAt = new Date(pair.expires_at).getTime();
	if (browser) localStorage.setItem(REFRESH_KEY, pair.refresh_token);
}

export function clearTokens(): void {
	accessToken = null;
	refreshToken = null;
	expiresAt = 0;
	if (browser) localStorage.removeItem(REFRESH_KEY);
}

async function doRefresh(): Promise<boolean> {
	if (refreshToken === null) return false;
	const res = await fetch('/api/auth/refresh', {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify({ refresh_token: refreshToken })
	});
	if (!res.ok) {
		clearTokens();
		return false;
	}
	setTokens((await res.json()) as TokenPair);
	return true;
}

/** One refresh in flight at a time; concurrent callers await the same result. */
function refreshOnce(): Promise<boolean> {
	if (refreshing === null) {
		refreshing = doRefresh().finally(() => {
			refreshing = null;
		});
	}
	return refreshing;
}

function withBearer(init: RequestInit): RequestInit {
	const headers = new Headers(init.headers);
	if (accessToken !== null) headers.set('authorization', `Bearer ${accessToken}`);
	return { ...init, headers };
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
	// Proactive refresh on the happy path (FAUTH-R5).
	if (accessToken !== null && expiresAt - Date.now() < PROACTIVE_MS) {
		await refreshOnce();
	}
	const res = await fetch(path, withBearer(init));
	if (res.status !== 401) return res;

	const refreshed = await refreshOnce(); // single-flight (FAUTH-R4)
	if (!refreshed) return res;
	return fetch(path, withBearer(init)); // one retry (FAUTH-R3)
}
