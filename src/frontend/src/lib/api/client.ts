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

// Admin-facing errors/warnings (admin-only feed, 4.B0+); copyable as {type,title,description}.
export interface AdminError {
	source: string;
	type: 'error' | 'warning';
	title: string;
	description: string;
}

export interface Health {
	status: string;
	db: string;
	version: string;
	// ISO8601 with the server's TZ offset (4.F1): the schedule timeline's clock source.
	server_time: string;
	worker_heartbeat_age_s: number | null;
}

// Plugin discovery (REG-R6): enabled + loaded plugins, no internal paths.
export interface PluginInfo {
	name: string;
	type: 'scraper' | 'notifier';
	route_base: string | null;
	icon: string | null;
	display_name: string;
	version: string;
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

// Admin-only errors/warnings feed (admin token required: 403 user, 401 anonymous).
// Never on the public /api/health.
export function getAdminErrors(): Promise<AdminError[]> {
	return apiFetch('/api/admin/errors').then(asJson<AdminError[]>);
}

// Dev feature flags (4.B1a/4.F6): a dynamic key -> params map. Admin-only, non-persistent.
// The UI renders inputs from the value types, so new flags appear with no frontend change.
export type FeatureFlags = Record<string, Record<string, unknown>>;

export function getFeatureFlags(): Promise<FeatureFlags> {
	return apiFetch('/api/admin/feature-flags').then(asJson<FeatureFlags>);
}

export async function patchFeatureFlags(partial: FeatureFlags): Promise<FeatureFlags> {
	const res = await apiFetch('/api/admin/feature-flags', {
		method: 'PATCH',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify(partial)
	});
	return asJson<FeatureFlags>(res);
}

// Admin scraper management (4.B2/4.B10). Admin-only on the backend.
export interface ScraperListItem {
	scraper_id: string;
	display_name: string;
	times: string[]; // daily slots "HH:MM:SS" (4.B2/4.F1)
	enabled: boolean;
	last_slot: string | null;
	cache_entries: number; // scrape-cache rows for this scraper
}

// Core reserved config a scraper's runs/scrape-now obey (4.B10).
export interface ScraperConfig {
	politeness_delay_ms: number;
	http_timeout_s: number;
	cache_ttl_min: number; // 0 disables the scrape cache
	scrape_now_min_interval_s: number;
}

export function listScrapers(): Promise<ScraperListItem[]> {
	return apiFetch('/api/admin/scrapers').then(asJson<ScraperListItem[]>);
}

// Set a scraper's daily times + enabled flag (4.B2/4.F1). The backend de-dupes, sorts and
// returns canonical HH:MM:SS times. 404 if the scraper isn't schedulable.
export async function updateScraperSchedule(
	id: string,
	body: { times: string[]; enabled: boolean }
): Promise<ScraperListItem> {
	const res = await apiFetch(`/api/admin/scrapers/${id}`, {
		method: 'PUT',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify(body)
	});
	return asJson<ScraperListItem>(res);
}

export function getScraperConfig(id: string): Promise<ScraperConfig> {
	return apiFetch(`/api/admin/scrapers/${id}/config`).then(asJson<ScraperConfig>);
}

export async function patchScraperConfig(
	id: string,
	partial: Partial<ScraperConfig>
): Promise<ScraperConfig> {
	const res = await apiFetch(`/api/admin/scrapers/${id}/config`, {
		method: 'PATCH',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify(partial)
	});
	return asJson<ScraperConfig>(res);
}

// Clear a scraper's scrape cache (4.B9/4.F5); returns how many entries were removed.
export async function clearScraperCache(id: string): Promise<{ deleted: number }> {
	const res = await apiFetch(`/api/admin/scrapers/${id}/cache`, { method: 'DELETE' });
	return asJson<{ deleted: number }>(res);
}

// System log (4.B7/4.F3-F4). Admin-only. Two reads: paged history + a live cursor tail.
export interface SystemLogEntry {
	id: number;
	created_at: string;
	level: 'info' | 'warning' | 'error';
	source: string;
	message: string;
	context: Record<string, unknown> | null;
}

export interface SystemLogPage {
	items: SystemLogEntry[];
	total: number;
	counts: Record<string, number>; // rows per level over the source/search filters
	sources: string[]; // distinct sources present (filter chips)
}

export interface LogQuery {
	page?: number;
	size?: number;
	level?: 'info' | 'warning' | 'error' | null;
	sources?: string[];
	q?: string;
	since?: number;
	limit?: number;
}

function logParams(query: LogQuery): URLSearchParams {
	const p = new URLSearchParams();
	if (query.page) p.set('page', String(query.page));
	if (query.size) p.set('size', String(query.size));
	if (query.level) p.set('level', query.level);
	if (query.q) p.set('q', query.q);
	if (query.since !== undefined) p.set('since', String(query.since));
	if (query.limit) p.set('limit', String(query.limit));
	for (const s of query.sources ?? []) p.append('sources', s);
	return p;
}

// Paged history (Live off): newest-first window + total + per-level counts + distinct sources.
export function getLogsPage(query: LogQuery = {}): Promise<SystemLogPage> {
	return apiFetch(`/api/admin/logs/page?${logParams(query)}`).then(asJson<SystemLogPage>);
}

// Live tail (cursor): no `since` → latest N (ascending); `since=<id>` → newer rows (ascending).
export function tailLogs(query: LogQuery = {}): Promise<SystemLogEntry[]> {
	return apiFetch(`/api/admin/logs?${logParams(query)}`).then(asJson<SystemLogEntry[]>);
}

// System settings (MNT-R3, 4.F7): runtime, DB-first, admin-only. Effective = defaults + overrides.
export interface SystemSettings {
	scraper_run_timeout_min: number;
	catchup_warning_min: number;
	log_retention_days: number;
	user_deletion_retention_days: number;
}

export function getSettings(): Promise<SystemSettings> {
	return apiFetch('/api/admin/settings').then(asJson<SystemSettings>);
}

export async function patchSettings(partial: Partial<SystemSettings>): Promise<SystemSettings> {
	const res = await apiFetch('/api/admin/settings', {
		method: 'PATCH',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify(partial)
	});
	return asJson<SystemSettings>(res);
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
	tags: string[];
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
