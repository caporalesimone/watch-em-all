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

// Carts (phase 5). Money fields are exact strings (Decimal). The cards carry the
// engine's computed state; the detail adds the member rows.
export type CartMode = 'cross' | 'scraper_specific';

export interface CartAdjustment {
	id: string; // full i18n key the UI localizes
	description: string; // debug-only
	amount: string; // signed: + saving, − cost
	params: Record<string, string>;
}

export interface CartThreshold {
	amount: string;
	current: string;
	reached: boolean;
	partial: boolean;
}

export interface CartMember {
	product_id: number;
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
	active: boolean;
}

export interface CartCard {
	id: number;
	name: string;
	mode: CartMode;
	scraper_id: string | null;
	currency: string | null;
	member_count: number;
	active_count: number;
	excluded_count: number;
	has_delisted: boolean;
	any_on_sale: boolean;
	all_on_sale: boolean;
	total_full: string;
	total_discounted: string;
	adjustments: CartAdjustment[];
	final_price: string;
	threshold_amount: string | null;
	threshold: CartThreshold | null;
	alert_types: string[];
	created_at: string;
}

export interface CartDetail extends CartCard {
	members: CartMember[];
}

export function listCarts(): Promise<CartCard[]> {
	return apiFetch('/api/carts').then(asJson<CartCard[]>);
}

export function getCart(id: number): Promise<CartDetail> {
	return apiFetch(`/api/carts/${id}`).then(asJson<CartDetail>);
}

export async function createCart(payload: {
	name: string;
	mode: CartMode;
	scraper_id?: string | null;
}): Promise<CartDetail> {
	const res = await apiFetch('/api/carts', {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify(payload)
	});
	return asJson<CartDetail>(res);
}

// PATCH: omit a field to leave it unchanged; send threshold_amount: null to clear it.
export async function patchCart(
	id: number,
	payload: { name?: string; threshold_amount?: string | null }
): Promise<CartDetail> {
	const res = await apiFetch(`/api/carts/${id}`, {
		method: 'PATCH',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify(payload)
	});
	return asJson<CartDetail>(res);
}

export async function deleteCart(id: number): Promise<void> {
	await asEmpty(await apiFetch(`/api/carts/${id}`, { method: 'DELETE' }));
}

export async function addCartItems(id: number, productIds: number[]): Promise<CartDetail> {
	const res = await apiFetch(`/api/carts/${id}/items`, {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify({ product_ids: productIds })
	});
	return asJson<CartDetail>(res);
}

export async function removeCartItems(id: number, productIds: number[]): Promise<CartDetail> {
	const res = await apiFetch(`/api/carts/${id}/items`, {
		method: 'DELETE',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify({ product_ids: productIds })
	});
	return asJson<CartDetail>(res);
}

// Replace the cart's enabled alert types with the full set (6.B1). Presence = enabled;
// pass [] to disable all.
export async function setCartAlertTypes(id: number, alertTypes: string[]): Promise<CartDetail> {
	const res = await apiFetch(`/api/carts/${id}/alert-types`, {
		method: 'PUT',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify({ alert_types: alertTypes })
	});
	return asJson<CartDetail>(res);
}

// Alert history (6.B8). Money is Decimal-as-string; dates are ISO-8601.
export interface AlertDigestProduct {
	product_id: number;
	name: string;
	url: string;
	plugin_id: string;
	tags: string[];
	price_previous: string | null;
	price_current: string;
	discount_pct: string;
	currency: string;
}

export interface AlertDigestThreshold {
	target: string;
	current: string;
	reached: boolean;
	partial: boolean;
	excluded: string[];
}

export interface AlertDigestCart {
	cart_id: number;
	cart_name: string;
	mode: string;
	cart_events: string[];
	products: AlertDigestProduct[];
	totals: { full: string; discounted: string; final: string };
	threshold: AlertDigestThreshold | null;
}

export interface AlertDigestPayload {
	kind: string;
	user_id: number;
	generated_at: string;
	cart_alerts: AlertDigestCart[];
}

export interface AlertListItem {
	id: number;
	kind: string;
	created_at: string;
	read: boolean;
	cart_count: number;
}

export interface AlertPage {
	items: AlertListItem[];
	total: number;
	page: number;
	page_size: number;
}

export interface AlertDelivery {
	plugin_id: string;
	status: string; // pending | delivered | failed | skipped | skipped_no_notifier
	error: string | null;
	updated_at: string;
}

export interface AlertDetail {
	id: number;
	kind: string;
	created_at: string;
	read: boolean;
	payload: AlertDigestPayload;
	deliveries: AlertDelivery[];
}

export function listAlerts(
	params: { page?: number; page_size?: number; kind?: string } = {}
): Promise<AlertPage> {
	const q = new URLSearchParams();
	if (params.page) q.set('page', String(params.page));
	if (params.page_size) q.set('page_size', String(params.page_size));
	if (params.kind) q.set('kind', params.kind);
	const qs = q.toString();
	return apiFetch(`/api/alerts${qs ? `?${qs}` : ''}`).then(asJson<AlertPage>);
}

export function getAlert(id: number): Promise<AlertDetail> {
	return apiFetch(`/api/alerts/${id}`).then(asJson<AlertDetail>);
}

export async function markAlertRead(id: number): Promise<void> {
	await asEmpty(await apiFetch(`/api/alerts/${id}/read`, { method: 'POST' }));
}

// Bulk-delete the user's own alerts (6.F3). Ids not owned by the caller are ignored.
export async function deleteAlerts(ids: number[]): Promise<void> {
	await asEmpty(
		await apiFetch('/api/alerts', {
			method: 'DELETE',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify({ ids })
		})
	);
}

export function getUnreadCount(): Promise<number> {
	return apiFetch('/api/alerts/unread-count')
		.then(asJson<{ count: number }>)
		.then((r) => r.count);
}

// Notifier channels (phase 7). One declarative form model drives both the user and admin forms;
// `label_key`/`help_key` are i18n keys, resolved with a humanized fallback when undefined (V1).
export interface ConfigField {
	key: string;
	label_key: string;
	type: 'text' | 'email' | 'password' | 'url' | 'number' | 'bool' | 'select';
	required: boolean;
	secret: boolean;
	placeholder: string | null;
	help_key: string | null;
	options: string[] | null;
	default: string | number | boolean | null;
}

// A channel as the user's Profile sees it (composite state + personal schema; secrets write-only).
export interface NotifierChannel {
	plugin_id: string;
	display_name: string;
	is_in_app: boolean;
	user_schema: ConfigField[];
	config: Record<string, unknown>; // non-secret stored values only
	is_set: Record<string, boolean>; // per secret: whether a value is stored
	available: boolean;
	user_config_complete: boolean;
	enabled: boolean;
	active: boolean;
}

// A channel as the admin's page sees it (system schema + kill-switch).
export interface AdminNotifier {
	plugin_id: string;
	display_name: string;
	is_in_app: boolean;
	admin_schema: ConfigField[];
	user_schema: ConfigField[]; // for the admin channel-test target
	config: Record<string, unknown>;
	is_set: Record<string, boolean>;
	enabled: boolean; // the admin kill-switch (PCFG-R8)
	admin_config_complete: boolean;
}

export interface NotifierTestResult {
	ok: boolean;
	error: string | null;
}

export function listNotifiers(): Promise<NotifierChannel[]> {
	return apiFetch('/api/notifiers').then(asJson<NotifierChannel[]>);
}

export async function setNotifierConfig(
	id: string,
	config: Record<string, unknown>
): Promise<NotifierChannel> {
	const res = await apiFetch(`/api/notifiers/${id}/config`, {
		method: 'PUT',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify({ config })
	});
	return asJson<NotifierChannel>(res);
}

export async function setNotifierEnabled(id: string, enabled: boolean): Promise<NotifierChannel> {
	const res = await apiFetch(`/api/notifiers/${id}`, {
		method: 'PATCH',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify({ enabled })
	});
	return asJson<NotifierChannel>(res);
}

export function testNotifier(id: string): Promise<NotifierTestResult> {
	return apiFetch(`/api/notifiers/${id}/test`, { method: 'POST' }).then(asJson<NotifierTestResult>);
}

export function listAdminNotifiers(): Promise<AdminNotifier[]> {
	return apiFetch('/api/admin/notifiers').then(asJson<AdminNotifier[]>);
}

export async function setAdminNotifierConfig(
	id: string,
	config: Record<string, unknown>
): Promise<AdminNotifier> {
	const res = await apiFetch(`/api/admin/notifiers/${id}/config`, {
		method: 'PUT',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify({ config })
	});
	return asJson<AdminNotifier>(res);
}

export async function setAdminNotifierEnabled(
	id: string,
	enabled: boolean
): Promise<AdminNotifier> {
	const res = await apiFetch(`/api/admin/notifiers/${id}`, {
		method: 'PATCH',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify({ enabled })
	});
	return asJson<AdminNotifier>(res);
}

export async function testAdminNotifier(
	id: string,
	config: Record<string, unknown>
): Promise<NotifierTestResult> {
	const res = await apiFetch(`/api/admin/notifiers/${id}/test`, {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify({ config })
	});
	return asJson<NotifierTestResult>(res);
}
