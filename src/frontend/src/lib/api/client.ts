// Typed API client (FE-4): the only place that builds requests; goes through the
// Auth Manager so no component touches a token. Errors surface as ApiErr carrying
// the backend {detail, code} envelope.
import { apiFetch, clearTokens, setTokens } from '$lib/auth/manager';

export interface Me {
	id: number;
	username: string;
	first_name: string;
	last_name: string;
	role: string;
	locale: string;
	must_change_password: boolean;
}

interface TokenPair {
	access_token: string;
	refresh_token: string;
	expires_at: string;
}

export interface Health {
	status: string;
	db: string;
	version: string;
	worker_heartbeat_age_s: number | null;
}

// Plugin discovery (REG-R6): enabled + loaded plugins, no internal paths.
export interface PluginInfo {
	name: string;
	type: 'scraper' | 'notifier';
	route_base: string | null;
	icon: string | null;
	display_name: string;
}

// Public endpoint; returns its body on 200 and 503 alike (we only want `version`).
export async function getHealth(): Promise<Health> {
	const res = await fetch('/api/health');
	return (await res.json()) as Health;
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

export function getPlugins(): Promise<PluginInfo[]> {
	return apiFetch('/api/plugins').then(asJson<PluginInfo[]>);
}

// Catalog / Product Picker (CAT-*). Money fields are Decimal serialised as
// strings (exact, no float drift) — rendered as-is, never parsed for maths.
export interface BrandRef {
	text: string;
	link: string | null;
}

export interface CategoryRef {
	text: string;
	link: string | null;
}

export interface CatalogItem {
	id: number;
	plugin_id: string;
	external_id: string;
	url: string;
	name: string;
	image_url: string | null;
	brand: BrandRef | null;
	product_properties: string[];
	category: CategoryRef[];
	currency: string;
	price_current: string;
	price_original: string;
	discount_pct: string;
	is_available: boolean;
	removed: boolean;
	extra: Record<string, unknown>;
	first_seen_at: string;
	last_seen_at: string;
}

export interface CatalogPage {
	items: CatalogItem[];
	total: number;
	page: number;
	page_size: number;
}

export type CatalogSort =
	| 'name'
	| 'plugin_id'
	| 'price_current'
	| 'price_original'
	| 'is_available'
	| 'last_seen_at';

export interface CatalogQuery {
	page?: number;
	page_size?: number;
	sort?: CatalogSort;
	order?: 'asc' | 'desc';
	q?: string;
	available?: boolean;
	removed?: boolean;
}

export function listCatalog(query: CatalogQuery = {}): Promise<CatalogPage> {
	const p = new URLSearchParams();
	if (query.page) p.set('page', String(query.page));
	if (query.page_size) p.set('page_size', String(query.page_size));
	if (query.sort) p.set('sort', query.sort);
	if (query.order) p.set('order', query.order);
	if (query.q) p.set('q', query.q);
	if (query.available !== undefined) p.set('available', String(query.available));
	if (query.removed !== undefined) p.set('removed', String(query.removed));
	const qs = p.toString();
	return apiFetch(`/api/catalog${qs ? `?${qs}` : ''}`).then(asJson<CatalogPage>);
}

// Admin user management (USR-*): create + list. Admin-only on the backend.
export interface AdminUser {
	id: number;
	username: string;
	first_name: string;
	last_name: string;
	role: string;
	is_active: boolean;
	must_change_password: boolean;
	last_login_at: string | null;
	created_at: string;
}

export interface NewUser {
	username: string;
	first_name: string;
	last_name: string;
	role: 'user' | 'admin';
	temp_password: string;
}

export function listUsers(): Promise<AdminUser[]> {
	return apiFetch('/api/admin/users').then(asJson<AdminUser[]>);
}

export async function createUser(payload: NewUser): Promise<AdminUser> {
	const res = await apiFetch('/api/admin/users', {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify(payload)
	});
	return asJson<AdminUser>(res);
}

// oldPassword is required for a normal change and omitted for the forced first
// change (must_change_password), which the backend accepts without it (auth.md).
export async function changePassword(newPassword: string, oldPassword?: string): Promise<void> {
	const payload: Record<string, string> = { new_password: newPassword };
	if (oldPassword !== undefined) payload.old_password = oldPassword;
	const res = await apiFetch('/api/auth/change-password', {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify(payload)
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
