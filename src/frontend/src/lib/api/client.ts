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
	/** Where this account is reached — the username itself, for everyone but the bootstrap admin. */
	notification_email: string;
	/** Only the bootstrap admin may change it: everyone else's address *is* their username. */
	email_editable: boolean;
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

/** Update the current profile. Only the bootstrap admin may send `contact_email` (10.F17). */
export async function patchMe(body: { contact_email?: string; locale?: string }): Promise<Me> {
	const res = await apiFetch('/api/me', {
		method: 'PATCH',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify(body)
	});
	return asJson<Me>(res);
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

// The settings a scraper declares for itself (10.B22). Schema and values together, because
// the form is rendered from the schema and there is nothing to show without it.
export interface PluginConfig {
	scraper_id: string;
	schema_fields: ConfigField[];
	config: Record<string, unknown>;
}

export function getScraperPluginConfig(id: string): Promise<PluginConfig> {
	return apiFetch(`/api/admin/scrapers/${id}/plugin-config`).then(asJson<PluginConfig>);
}

export async function setScraperPluginConfig(
	id: string,
	config: Record<string, unknown>
): Promise<PluginConfig> {
	const res = await apiFetch(`/api/admin/scrapers/${id}/plugin-config`, {
		method: 'PUT',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify({ config })
	});
	return asJson<PluginConfig>(res);
}

// What a scraper has done since `since` (10.B20). Cumulative and pruning-proof: the Runs page
// answers "recently", this answers "ever".
export interface LifetimeStats {
	plugin_id: string;
	since: string;
	runs_total: number;
	runs_ok: number;
	runs_failed: number;
	runs_skipped_locked: number;
	consecutive_failures: number;
	last_run_at: string | null;
	last_success_at: string | null;
	last_failure_at: string | null;
	http_requests_total: number;
	cache_hits_total: number;
	bytes_downloaded_total: number;
	politeness_wait_s_total: number;
	run_seconds_total: number;
	rate_limited_total: number;
	gate_hits_total: number;
	gate_cleared_total: number;
	robots_denied_total: number;
	products_delivered_total: number;
	pages_fetched_total: number;
	parse_failures_total: number;
}

export function getLifetimeStats(id: string): Promise<LifetimeStats> {
	return apiFetch(`/api/admin/scrapers/${id}/lifetime-stats`).then(asJson<LifetimeStats>);
}

/** Zero the counters and restamp `since` (10.B21). Destructive, no history kept. */
export async function resetLifetimeStats(id: string): Promise<LifetimeStats> {
	const res = await apiFetch(`/api/admin/scrapers/${id}/lifetime-stats/reset`, { method: 'POST' });
	return asJson<LifetimeStats>(res);
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
	// Fixed options, not free days (10.B19): 0 = never.
	password_expiry_days: 0 | 30 | 90 | 180 | 365;
	// The nightly maintenance window and what it leaves behind (10.B8a/b).
	maintenance_hour: number;
	alert_keep_last: number;
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
	// Which of the user's inputs still deliver this product (C14). Empty = nothing does, so a
	// deletion is final; otherwise these are what will bring it back on the next scan.
	sources: CatalogItemSource[];
	// How many of the user's carts hold it: deleting it takes it out of all of them, silently
	// (CART-R8), so a confirmation has to be able to count it (C7).
	in_carts: number;
}

export interface CatalogItemSource {
	kind: string; // the plugin's vocabulary (Dragon Store: 'product' | 'category')
	label: string; // a name to show, kept current by the backend
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

// Catalog cleanups (9.B7/9.F4). Each answers a different intention — tidy up what the site
// no longer offers, drop this one, start over — and each returns how many rows went, because
// "nothing was delisted" and "twelve products went" are different answers to the same click.
export interface RemovedCount {
	removed: number;
}

export function removeDelistedProducts(): Promise<RemovedCount> {
	return apiFetch('/api/catalog/delisted', { method: 'DELETE' }).then(asJson<RemovedCount>);
}

// What that removal is about to do, before it does it (C7): every delisted row, and how many of
// them are in a cart. Counted server-side over the whole catalog, not the visible page.
export interface DelistedSummary {
	total: number;
	in_carts: number;
}

export function getDelistedSummary(): Promise<DelistedSummary> {
	return apiFetch('/api/catalog/delisted').then(asJson<DelistedSummary>);
}

export function removeCatalogProduct(productId: number): Promise<RemovedCount> {
	return apiFetch(`/api/catalog/${productId}`, { method: 'DELETE' }).then(asJson<RemovedCount>);
}

export function emptyCatalog(): Promise<RemovedCount> {
	return apiFetch('/api/catalog', { method: 'DELETE' }).then(asJson<RemovedCount>);
}

// Price history (HIST-*). Series are served ready for the chart (the SPA does not
// aggregate). Money is Decimal serialised as a string; parse only for plotting.
export type HistoryRange = 'week' | 'month' | 'all';

export interface PricePoint {
	t: string;
	price: string;
	available: boolean;
}

export interface ProductHistory {
	product_id: number;
	range: HistoryRange;
	points: PricePoint[];
}

export function getProductHistory(productId: number, range: HistoryRange): Promise<ProductHistory> {
	return apiFetch(`/api/products/${productId}/history?range=${range}`).then(asJson<ProductHistory>);
}

export interface CartPricePoint {
	t: string;
	total: string;
}

export interface CartHistory {
	cart_id: number;
	range: HistoryRange;
	points: CartPricePoint[];
}

export function getCartHistory(cartId: number, range: HistoryRange): Promise<CartHistory> {
	return apiFetch(`/api/carts/${cartId}/history?range=${range}`).then(asJson<CartHistory>);
}

// Admin user management (USR-*): create + list. Admin-only on the backend.
export interface DashboardTotals {
	users_total: number;
	users_active: number;
	users_deleting: number;
	products_total: number;
	products_delisted: number;
	carts_total: number;
	price_history_rows: number;
	watched_scrapers: number;
}

export interface DashboardNotifications {
	window_days: number;
	alerts: number;
	delivered: number;
	failed: number;
	skipped: number;
}

export interface DashboardResponse {
	totals: DashboardTotals;
	notifications: DashboardNotifications;
}

export interface UserLoadRow {
	user_id: number;
	username: string | null;
	scraper_id: string | null;
	products: number;
	carts: number;
	http_requests: number;
	cache_hits: number;
}

export interface DashboardUsers {
	window_days: number;
	by_user: UserLoadRow[];
	by_user_and_scraper: UserLoadRow[];
}

export function getDashboard(windowDays: number): Promise<DashboardResponse> {
	return apiFetch(`/api/admin/dashboard?window_days=${windowDays}`).then(asJson<DashboardResponse>);
}

export function getDashboardUsers(windowDays: number): Promise<DashboardUsers> {
	return apiFetch(`/api/admin/dashboard/users?window_days=${windowDays}`).then(
		asJson<DashboardUsers>
	);
}

export interface CalendarSlot {
	scraper_id: string;
	at: string;
	enabled: boolean;
	avg_seconds: number | null;
}

export interface CalendarDay {
	date: string;
	slots: CalendarSlot[];
}

export function getScraperCalendar(date: string): Promise<CalendarDay> {
	return apiFetch(`/api/admin/scrapers/calendar?date=${date}`).then(asJson<CalendarDay>);
}

export interface RunSummary {
	run_id: number;
	scraper_id: string;
	trigger: string;
	slot: string | null;
	started_at: string;
	finished_at: string | null;
	status: string;
	users_processed: number;
	products_found: number;
	products_new: number;
	price_changes: number;
	products_removed: number;
	products_excluded: number;
	http_requests: number;
	cache_hits: number;
	error_message: string | null;
}

export interface RunUserDetail {
	user_id: number;
	username: string | null;
	started_at: string;
	finished_at: string | null;
	status: string;
	products_found: number;
	products_new: number;
	price_changes: number;
	http_requests: number;
	cache_hits: number;
	error_message: string | null;
}

export interface RunPage {
	items: RunSummary[];
	total: number;
}

export function listRuns(opts?: {
	scraperId?: string | null;
	status?: string | null;
	/** Scheduled (the server's default), manual, or both (10.B20). */
	trigger?: 'scheduled' | 'manual' | 'all';
	page?: number;
	pageSize?: number;
}): Promise<RunPage> {
	const q = new URLSearchParams();
	if (opts?.scraperId) q.set('scraper_id', opts.scraperId);
	if (opts?.status) q.set('status', opts.status);
	if (opts?.trigger) q.set('trigger', opts.trigger);
	q.set('page', String(opts?.page ?? 1));
	q.set('page_size', String(opts?.pageSize ?? 25));
	return apiFetch(`/api/admin/runs?${q}`).then(asJson<RunPage>);
}

export function getRunDetail(runId: number): Promise<RunUserDetail[]> {
	return apiFetch(`/api/admin/runs/${runId}`).then(asJson<RunUserDetail[]>);
}

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
	// Deferred deletion (10.B3): both null on a normal account, both set once marked.
	deletion_marked_at: string | null;
	deletion_due_at: string | null;
}

export type UserStatusFilter = 'active' | 'disabled' | 'deleting';
/** Every column of the Users table (10.F28). Role and status are ranked, not alphabetical. */
export type UserSort =
	| 'username'
	| 'name'
	| 'role'
	| 'status'
	| 'last_login'
	| 'marked_at'
	| 'due_at';

export interface NewUser {
	/** The account's email address, which is also its username (10.B23). */
	username: string;
	first_name: string;
	last_name: string;
	role: 'user' | 'admin';
}

export function listUsers(opts?: {
	status?: UserStatusFilter | null;
	sort?: UserSort;
	order?: 'asc' | 'desc';
}): Promise<AdminUser[]> {
	const query = new URLSearchParams();
	if (opts?.status) query.set('status', opts.status);
	if (opts?.sort) query.set('sort', opts.sort);
	if (opts?.order) query.set('order', opts.order);
	const suffix = query.toString() ? `?${query}` : '';
	return apiFetch(`/api/admin/users${suffix}`).then(asJson<AdminUser[]>);
}

/** The server generates the new password and mails it (10.B24) — nothing to send, nothing back. */
export async function resetUserPassword(id: number): Promise<AdminUser> {
	const res = await apiFetch(`/api/admin/users/${id}/reset-password`, { method: 'POST' });
	return asJson<AdminUser>(res);
}

export async function setUserActive(id: number, isActive: boolean): Promise<AdminUser> {
	const res = await apiFetch(`/api/admin/users/${id}`, {
		method: 'PATCH',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify({ is_active: isActive })
	});
	return asJson<AdminUser>(res);
}

export async function markUserForDeletion(id: number): Promise<AdminUser> {
	const res = await apiFetch(`/api/admin/users/${id}`, { method: 'DELETE' });
	return asJson<AdminUser>(res);
}

export async function restoreUser(id: number): Promise<AdminUser> {
	const res = await apiFetch(`/api/admin/users/${id}/restore`, { method: 'POST' });
	return asJson<AdminUser>(res);
}

/**
 * Delete an already-marked account now, deadline waived (10.B27). Answers 204 with no body:
 * there is no account left to describe, so the caller reloads the list rather than patching a
 * row it still holds.
 */
export async function purgeUser(id: number): Promise<void> {
	await apiFetch(`/api/admin/users/${id}/purge`, { method: 'DELETE' });
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
	// The Difference column, already rendered by the backend (C19), so the email and this page
	// cannot disagree. `null` = nothing to report (no previous price, or the product is
	// delisted), which both render as an em dash.
	difference: string | null;
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

// A text notification — an admin message or a core-generated one (AEV-R6). `body` is the
// Markdown as written; `body_html` is that body already rendered and sanitised by the core, the
// same helper the email uses, so the two channels cannot say the message differently.
export interface TextMessagePayload {
	kind: string;
	user_id: number;
	generated_at: string;
	title: string;
	body: string;
	body_html?: string;
}

export type NotificationPayload = AlertDigestPayload | TextMessagePayload;

export function isTextMessage(p: NotificationPayload): p is TextMessagePayload {
	return p.kind === 'admin_message' || p.kind === 'system_message';
}

// The two categories a user sees (ADMSG-R4), derived from the kind and never stored.
export function notificationCategory(kind: string): 'admin' | 'system' {
	return kind === 'admin_message' ? 'admin' : 'system';
}

export interface AlertListItem {
	id: number;
	// Which table the id belongs to (10.B12). The history is a union of the user's own rows and
	// the shared announcements, so an id alone does not identify a notification.
	source: 'alert' | 'broadcast';
	kind: string;
	created_at: string;
	read: boolean;
	cart_count: number;
	// Present for the text kinds only: a digest has no title, its preview is the cart count.
	title: string | null;
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
	source: 'alert' | 'broadcast';
	kind: string;
	created_at: string;
	read: boolean;
	payload: NotificationPayload;
	deliveries: AlertDelivery[];
}

export function listAlerts(
	params: {
		page?: number;
		page_size?: number;
		kind?: string;
		category?: 'system' | 'admin';
	} = {}
): Promise<AlertPage> {
	const q = new URLSearchParams();
	if (params.page) q.set('page', String(params.page));
	if (params.page_size) q.set('page_size', String(params.page_size));
	if (params.kind) q.set('kind', params.kind);
	if (params.category) q.set('category', params.category);
	const qs = q.toString();
	return apiFetch(`/api/alerts${qs ? `?${qs}` : ''}`).then(asJson<AlertPage>);
}

export function getAlert(id: number): Promise<AlertDetail> {
	return apiFetch(`/api/alerts/${id}`).then(asJson<AlertDetail>);
}

// An announcement, which lives in its own table and so has its own id space (10.B12).
export function getBroadcast(id: number): Promise<AlertDetail> {
	return apiFetch(`/api/alerts/broadcasts/${id}`).then(asJson<AlertDetail>);
}

export async function markAlertRead(id: number): Promise<void> {
	await asEmpty(await apiFetch(`/api/alerts/${id}/read`, { method: 'POST' }));
}

// Advance the read pointer. Monotone by construction: marking a recent announcement read also
// clears the older ones, which is the accepted shape of the one-row-per-broadcast design.
export async function markBroadcastRead(id: number): Promise<void> {
	await asEmpty(await apiFetch(`/api/alerts/broadcasts/${id}/read`, { method: 'POST' }));
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

// Admin messages (10.B12/10.B13/10.F9). ------------------------------------------------------

export interface MessageOutcomeCounts {
	delivered: number;
	pending: number;
	failed: number;
	skipped: number;
}

export interface AdminMessageSummary {
	id: number;
	audience: 'all' | 'user';
	target_user_id: number | null;
	target_username: string | null;
	title: string;
	body: string;
	recipient_count: number;
	created_at: string;
	sender_username: string | null;
	outcomes: MessageOutcomeCounts;
	/** How many recipients have opened it **in the app** (10.B30). An aggregate, never a name. */
	read_count: number;
}

export interface AdminMessagePage {
	items: AdminMessageSummary[];
	total: number;
	page: number;
	page_size: number;
}

export interface MessageRecipient {
	user_id: number;
	username: string;
	channels: AlertDelivery[];
}

export interface AdminMessageDetail extends AdminMessageSummary {
	recipients: MessageRecipient[];
}

/** Sent messages, newest first. `audience` narrows to broadcasts or one-to-one notes (10.F30). */
export function listAdminMessages(
	page = 1,
	pageSize = 20,
	audience: 'all' | 'user' | null = null
): Promise<AdminMessagePage> {
	const filter = audience ? `&audience=${audience}` : '';
	return apiFetch(`/api/admin/messages?page=${page}&page_size=${pageSize}${filter}`).then(
		asJson<AdminMessagePage>
	);
}

/**
 * Remove a sent message from the history (10.B29). Not an un-send: for a **broadcast** — one row
 * for everybody — it also disappears from every recipient's list, which is the point, since they
 * cannot delete it themselves. A targeted message leaves the recipient their own copy.
 */
export async function deleteAdminMessage(id: number): Promise<void> {
	await apiFetch(`/api/admin/messages/${id}`, { method: 'DELETE' });
}

export function getAdminMessage(id: number): Promise<AdminMessageDetail> {
	return apiFetch(`/api/admin/messages/${id}`).then(asJson<AdminMessageDetail>);
}

export async function sendAdminMessage(input: {
	title: string;
	body: string;
	target_user_id?: number | null;
}): Promise<AdminMessageSummary> {
	const res = await apiFetch('/api/admin/messages', {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify(input)
	});
	return asJson<AdminMessageSummary>(res);
}

// The Preview tab. Rendered by the server so it is the same HTML the recipients get — see the
// endpoint's own note on why there is no markdown-it in this bundle.
export async function previewMessage(body: string): Promise<string> {
	const res = await apiFetch('/api/admin/messages/preview', {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify({ body })
	});
	return (await asJson<{ body_html: string }>(res)).body_html;
}

// The system-message catalog (10.B17). One entry per key the core declares, whether or not an
// admin has rewritten it — so the list is the catalog, and `is_override` says which is which.
export interface MessageTemplate {
	key: string;
	title: string;
	body: string;
	default_title: string;
	default_body: string;
	placeholders: string[];
	required: string[];
	is_override: boolean;
	unknown_placeholders: string[];
}

export function listMessageTemplates(): Promise<MessageTemplate[]> {
	return apiFetch('/api/admin/message-templates').then(asJson<MessageTemplate[]>);
}

export async function saveMessageTemplate(
	key: string,
	title: string,
	body: string
): Promise<MessageTemplate> {
	const res = await apiFetch(`/api/admin/message-templates/${key}`, {
		method: 'PUT',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify({ title, body })
	});
	return asJson<MessageTemplate>(res);
}

/** Drop the override: the message goes back to the core's default (not a copy of it). */
export async function resetMessageTemplate(key: string): Promise<void> {
	await asEmpty(await apiFetch(`/api/admin/message-templates/${key}`, { method: 'DELETE' }));
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
	/** How much of a row the field asks for (10.F26). Optional here so a schema stored or
	 *  mocked before the field existed still renders — missing reads as `full`. */
	width?: 'full' | 'half' | 'third' | 'quarter';
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
	/** Whether this channel must prove itself before it can be switched on (10.B28). */
	requires_validation: boolean;
	/** Whether what is stored *now* is what was proven: a fingerprint match, not a flag. */
	validated: boolean;
	validated_at: string | null;
}

/** The outcome of a validation attempt, with the channel's fresh state beside it (10.B28). */
export interface NotifierValidationResult {
	ok: boolean;
	error: string | null;
	channel: AdminNotifier;
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

/**
 * Send a real message through the channel and, if the server takes it, record the settings as
 * validated (10.B28). The target is the admin's own account (10.B25) — the address the system
 * will really use. A failure records nothing.
 */
export async function validateAdminNotifier(id: string): Promise<NotifierValidationResult> {
	const res = await apiFetch(`/api/admin/notifiers/${id}/validate`, { method: 'POST' });
	return asJson<NotifierValidationResult>(res);
}
