// Typed API client (FE-4): the only place that builds requests; goes through the
// Auth Manager so no component touches a token. Errors surface as ApiErr carrying
// the backend {detail, code} envelope.
import { apiFetch, clearTokens, setTokens } from '$lib/auth/manager';

export interface Me {
	id: number;
	username: string;
	role: string;
	locale: string;
	must_change_password: boolean;
}

interface TokenPair {
	access_token: string;
	refresh_token: string;
	expires_at: string;
}

export class ApiErr extends Error {
	constructor(
		readonly status: number,
		readonly code: string,
		readonly detail: string
	) {
		super(detail);
		this.name = 'ApiErr';
	}
}

async function fail(res: Response): Promise<never> {
	let code = 'error';
	let detail = res.statusText;
	try {
		const body = (await res.json()) as { detail?: string; code?: string };
		if (body.code) code = body.code;
		if (body.detail) detail = body.detail;
	} catch {
		/* non-JSON error body */
	}
	throw new ApiErr(res.status, code, detail);
}

async function asJson<T>(res: Response): Promise<T> {
	if (!res.ok) return fail(res);
	return (await res.json()) as T;
}

async function asEmpty(res: Response): Promise<void> {
	if (!res.ok) await fail(res);
}

export async function login(username: string, password: string): Promise<void> {
	const res = await fetch('/api/auth/login', {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify({ username, password })
	});
	setTokens(await asJson<TokenPair>(res));
}

export async function logout(): Promise<void> {
	try {
		await asEmpty(await apiFetch('/api/auth/logout', { method: 'POST' }));
	} finally {
		clearTokens();
	}
}

export function getMe(): Promise<Me> {
	return apiFetch('/api/me').then(asJson<Me>);
}

export async function changePassword(oldPassword: string, newPassword: string): Promise<void> {
	const res = await apiFetch('/api/auth/change-password', {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify({ old_password: oldPassword, new_password: newPassword })
	});
	await asEmpty(res);
}

export async function updateLocale(locale: string): Promise<Me> {
	const res = await apiFetch('/api/me', {
		method: 'PATCH',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify({ locale })
	});
	return asJson<Me>(res);
}
