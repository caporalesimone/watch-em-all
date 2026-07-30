<script lang="ts">
	import { onDestroy, onMount } from 'svelte';

	import { apiFetch } from '$lib/auth/manager';
	import ProductCell from '$lib/components/ProductCell.svelte';
	import ProductTags from '$lib/components/ProductTags.svelte';
	import ProductThumb from '$lib/components/ProductThumb.svelte';
	import { dateTime } from '$lib/format';
	import { _ } from '$lib/i18n';
	import { isPrivileged } from '$lib/stores/auth';

	const BASE = '/api/plugins/dragon-store';
	// The label the sanitiser puts on a damaged listing. Read, never re-derived: the title
	// arrives with the label already stripped, so searching it again would find nothing.
	const DENTED_TAG = 'Ammaccato';

	// 9.F5: a manual scrape is the quickest way to send a site requests its Crawl-delay never
	// asked for, so it belongs to the levels that answer for it. The API refuses it too — this
	// only keeps the button (and its polling) out of a page that cannot use it.
	const canScrapeNow = $derived($isPrivileged);

	interface BrandRef {
		text: string;
		link: string | null;
	}
	interface CategoryRef {
		text: string;
		link: string | null;
	}
	interface Watch {
		id: number;
		kind: string;
		url: string;
		name: string | null;
		image_url: string | null;
		brand: BrandRef | null;
		tags: string[];
		category: CategoryRef[];
		status: string;
		status_detail: string | null;
		include_ammaccati: boolean;
		products_included: number;
		products_excluded: number;
		last_scanned_at: string | null;
	}
	interface ScrapeStatus {
		available: boolean;
		available_at: string | null;
		retry_after_seconds: number;
		interval_seconds: number;
	}

	interface Job {
		active: boolean;
		watch_id: number | null;
		kind: string | null;
		status: string | null;
		status_detail: string | null;
		progress_done: number;
		progress_total: number | null;
		queue_position: number;
		cancellable: boolean;
	}

	interface Classification {
		kind: string | null;
	}

	let watches = $state<Watch[]>([]);
	// What the backend says the pasted URL is (9.F2). Null while we have not asked, or when the
	// answer was "neither" — the two read the same on screen, because a URL nobody recognises
	// and a URL nobody has looked at yet are equally unusable.
	let detectedKind = $state<string | null>(null);
	let includeAmmaccati = $state(false);
	let classifyTimer: ReturnType<typeof setTimeout> | undefined;
	// The watch a finished job resolved (9.F3): the outcome panel reads the row, not the
	// response to the POST — the POST answered in milliseconds, minutes before this existed.
	let outcome = $state<Watch | null>(null);
	// The job that resolves an add lives in the database (9.X6b-e), not in this component:
	// that is the whole point — a reload re-reads it instead of losing it, and the form stays
	// blocked because the API refuses a second submission, not because a button is disabled.
	let job = $state<Job | null>(null);
	let jobTimer: ReturnType<typeof setInterval> | undefined;
	let url = $state('');
	let status = $state<ScrapeStatus | null>(null);
	let remaining = $state(0);
	let confirming = $state(false);
	let busy = $state(false);
	let notice = $state<string | null>(null);
	let error = $state<string | null>(null);

	let timer: ReturnType<typeof setInterval> | undefined;

	async function getJson<T>(path: string): Promise<T> {
		const res = await apiFetch(path);
		if (!res.ok) throw new Error(String(res.status));
		return (await res.json()) as T;
	}

	async function loadWatches(): Promise<void> {
		watches = await getJson<Watch[]>(`${BASE}/watches`);
	}

	async function loadJob(): Promise<void> {
		try {
			const next = await getJson<Job>(`${BASE}/watches/job`);
			const finished = job?.active && !next.active;
			const finishedId = job?.watch_id ?? null;
			job = next.active ? next : null;
			if (finished) {
				await loadWatches(); // it landed: show the resolved row
				// What came in, from the row the job left behind (9.F3).
				outcome = watches.find((w) => w.id === finishedId) ?? null;
			}
			if (next.active && jobTimer === undefined) startJobPolling();
			if (!next.active) stopJobPolling();
		} catch (err) {
			console.error('dragon_store: job status failed', err);
		}
	}

	function startJobPolling(): void {
		// A second is plenty: the steps are eleven seconds apart, by the site's own request.
		jobTimer = setInterval(() => void loadJob(), 1000);
	}

	function stopJobPolling(): void {
		if (jobTimer !== undefined) {
			clearInterval(jobTimer);
			jobTimer = undefined;
		}
	}

	async function cancelJob(): Promise<void> {
		if (job?.watch_id == null) return;
		await apiFetch(`${BASE}/watches/${job.watch_id}/cancel`, { method: 'POST' });
		await loadJob();
	}

	function applyStatus(s: ScrapeStatus): void {
		status = s;
		remaining = s.available ? 0 : s.retry_after_seconds;
	}

	async function loadStatus(): Promise<void> {
		applyStatus(await getJson<ScrapeStatus>(`${BASE}/scrape-now`));
	}

	onMount(() => {
		void loadWatches();
		// Not even asked for by a level that cannot scrape: the endpoint answers 403 (9.B8), and
		// polling it would log a refusal a second at a time.
		if (canScrapeNow) void loadStatus();
		// Ask once on mount: this is what makes a reload mid-resolution harmless.
		void loadJob();
		timer = setInterval(() => {
			if (status && !status.available && remaining > 0) {
				remaining -= 1;
				if (remaining <= 0) void loadStatus();
			}
		}, 1000);
	});
	onDestroy(() => {
		if (timer) clearInterval(timer);
		if (classifyTimer) clearTimeout(classifyTimer);
		stopJobPolling();
	});

	// --- what am I pasting? (9.F2) ---
	//
	// The backend answers, because the URL grammar is the plugin's: a copy of the rule here
	// would be free to drift from the one that decides what actually gets added. Debounced, so
	// a paste costs one question and typing costs few; the answer is dropped if the box changed
	// while it was in flight, which is what makes a slow reply harmless rather than misleading.
	function onUrlInput(): void {
		detectedKind = null;
		if (classifyTimer) clearTimeout(classifyTimer);
		const value = url.trim();
		if (!value) return;
		classifyTimer = setTimeout(() => void classify(value), 400);
	}

	async function classify(value: string): Promise<void> {
		try {
			const res = await getJson<Classification>(
				`${BASE}/classify?url=${encodeURIComponent(value)}`
			);
			if (url.trim() !== value) return; // the user kept typing: this answer is about the past
			detectedKind = res.kind;
			// The toggle disappears with the category it belonged to; leaving it set would send a
			// flag the backend then has to ignore.
			if (res.kind !== 'category') includeAmmaccati = false;
		} catch {
			detectedKind = null;
		}
	}

	async function setIncludeAmmaccati(watch: Watch, value: boolean): Promise<void> {
		error = null;
		const res = await apiFetch(`${BASE}/watches/${watch.id}`, {
			method: 'PATCH',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify({ include_ammaccati: value })
		});
		if (!res.ok) {
			const code = await res
				.json()
				.then((b) => b?.code as string | undefined)
				.catch(() => undefined);
			error = $_(code === 'watch_busy' ? 'dragon_store.watches.busy' : 'dragon_store.error');
		}
		// Either way, re-read: the checkbox must show what the server holds, not what was clicked.
		await loadWatches();
	}

	async function addWatch(event: Event): Promise<void> {
		event.preventDefault();
		error = null;
		notice = null;
		if (!url.trim()) {
			error = $_('dragon_store.watches.invalid');
			return;
		}
		// `busy` covers the POST itself, which is now a matter of milliseconds: since 9.X6b the
		// server commits the row and scrapes afterwards. It is not what stops a second
		// submission — the API does that, refusing with `add_in_progress` while one is in
		// flight, because a disabled button is not a rule and a reload used to throw it away.
		busy = true;
		outcome = null; // a new add: the previous outcome is no longer what the page is about
		try {
			const res = await apiFetch(`${BASE}/watches`, {
				method: 'POST',
				headers: { 'content-type': 'application/json' },
				body: JSON.stringify({ url: url.trim(), include_ammaccati: includeAmmaccati })
			});
			if (!res.ok) {
				const code = await res
					.json()
					.then((b) => b?.code as string | undefined)
					.catch(() => undefined);
				error = $_(
					code === 'duplicate_watch'
						? 'dragon_store.watches.duplicate'
						: code === 'add_in_progress'
							? 'dragon_store.watches.add_in_progress'
							: code === 'invalid_url'
								? 'dragon_store.watches.invalid_url'
								: 'dragon_store.error'
				);
				return;
			}
			url = '';
			detectedKind = null;
			includeAmmaccati = false;
			// The answer arrives before the scrape does: follow the job instead of waiting.
			await loadJob();
			await loadWatches();
		} finally {
			busy = false;
		}
	}

	async function removeWatch(id: number): Promise<void> {
		const res = await apiFetch(`${BASE}/watches/${id}`, { method: 'DELETE' });
		if (res.ok) await loadWatches();
	}

	async function doScrape(): Promise<void> {
		confirming = false;
		busy = true;
		error = null;
		notice = null;
		try {
			const res = await apiFetch(`${BASE}/scrape-now`, { method: 'POST' });
			if (res.status === 202) {
				notice = $_('dragon_store.scrape_now.started');
			} else if (res.status !== 429) {
				error = $_('dragon_store.error');
			}
			await loadStatus(); // refresh cooldown either way (202 -> on cooldown; 429 -> still)
		} catch {
			error = $_('dragon_store.error');
		} finally {
			busy = false;
		}
	}

	function fmt(total: number): string {
		const s = Math.max(0, Math.floor(total));
		const h = Math.floor(s / 3600);
		const m = Math.floor((s % 3600) / 60);
		const sec = s % 60;
		if (h > 0) return `${h}h ${String(m).padStart(2, '0')}m`;
		if (m > 0) return `${m}m ${String(sec).padStart(2, '0')}s`;
		return `${sec}s`;
	}

	function fmtInterval(total: number): string {
		const s = Math.floor(total);
		const h = Math.floor(s / 3600);
		const m = Math.floor((s % 3600) / 60);
		if (h > 0) return m > 0 ? `${h}h ${m}m` : `${h}h`;
		return m > 0 ? `${m}m` : `${s}s`;
	}

	const locked = $derived(status !== null && !status.available);
	const intervalLabel = $derived(status ? fmtInterval(status.interval_seconds) : '');

	// A category and a product are read differently and are worth telling apart at a glance:
	// one is a hundred products that come and go, the other is one product.
	function kindChip(kind: string): string {
		const base = 'rounded px-1.5 py-0.5 text-[11px] font-medium';
		return kind === 'category'
			? `${base} bg-indigo-100 text-indigo-700 dark:bg-indigo-900/50 dark:text-indigo-300`
			: `${base} bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300`;
	}

	const inputClass =
		'rounded border border-slate-300 bg-white px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-900';
	const btn =
		'rounded border border-slate-300 px-3 py-1 text-sm hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800';
</script>

<section class="space-y-8">
	<header class="space-y-4">
		<div class="flex items-center gap-2">
			<img src="/api/plugin-assets/dragon_store/icon" alt="" class="h-6 w-6" />
			<h1 class="text-xl font-semibold">{$_('dragon_store.title')}</h1>
		</div>
		<p class="max-w-prose text-sm text-slate-500">{$_('dragon_store.blurb')}</p>
	</header>

	<!-- Add a watch (3.F3): one scrape resolves the product AND stores it (0.8.1) -->
	<form onsubmit={addWatch} class="space-y-3">
		<div class="flex gap-2">
			<input
				class="{inputClass} flex-1"
				placeholder={$_('dragon_store.watches.url_placeholder')}
				bind:value={url}
				oninput={onUrlInput}
			/>
			<button
				type="submit"
				class="rounded bg-slate-800 px-3 py-1 text-sm text-white hover:bg-slate-700 disabled:opacity-50 dark:bg-slate-200 dark:text-slate-900 dark:hover:bg-white"
				disabled={busy}
			>
				{$_('dragon_store.watches.add')}
			</button>
		</div>
		<!--
			What the URL is, said before the add rather than after it (9.F2). The dented toggle
			exists only for a category: on a single product it would mean refusing the very page
			the user pasted, so it is not offered at all rather than offered and ignored.
		-->
		{#if url.trim() && detectedKind !== null}
			<div class="flex flex-wrap items-center gap-3 text-xs">
				<span class={kindChip(detectedKind)}>
					{detectedKind === 'category'
						? $_('dragon_store.watches.kind_category')
						: $_('dragon_store.watches.kind_product')}
				</span>
				{#if detectedKind === 'category'}
					<label class="flex items-center gap-2 text-slate-600 dark:text-slate-300">
						<input type="checkbox" bind:checked={includeAmmaccati} />
						{$_('dragon_store.watches.include_ammaccati')}
					</label>
					<span class="text-slate-400">{$_('dragon_store.watches.include_ammaccati_hint')}</span>
				{/if}
			</div>
		{/if}
		{#if job}
			<!--
				Read from the server, so a reload draws it again instead of losing it (9.X6e).
				Determinate as soon as the total is known: a category page states how many pages
				there are, and every step is one request, i.e. about eleven seconds of politeness.
				While queued it says *why* nothing is moving — "first in the queue" with nothing
				happening reads as a fault otherwise, which is the ambiguity 9.X2 was about.
			-->
			<div class="space-y-2 rounded border border-slate-200 p-3 dark:border-slate-800">
				<div class="flex items-center justify-between gap-2 text-sm">
					<span class="flex items-center gap-2 text-slate-500">
						<span
							class="h-3 w-3 animate-spin rounded-full border-2 border-slate-300 border-t-slate-600 dark:border-slate-600 dark:border-t-slate-300"
						></span>
						{#if job.status === 'queued'}
							{job.queue_position > 0
								? $_('dragon_store.watches.queued', {
										values: { position: job.queue_position }
									})
								: $_('dragon_store.watches.queued_next')}
						{:else}
							{job.status_detail ?? $_('dragon_store.watches.scraping')}
						{/if}
					</span>
					{#if job.cancellable}
						<button type="button" class={btn} onclick={cancelJob}>
							{$_('dragon_store.watches.cancel')}
						</button>
					{/if}
				</div>
				{#if job.progress_total}
					<div class="h-1.5 w-full overflow-hidden rounded bg-slate-200 dark:bg-slate-800">
						<div
							class="h-full bg-slate-600 transition-all duration-500 dark:bg-slate-300"
							style="width: {Math.min(
								100,
								Math.round((job.progress_done / job.progress_total) * 100)
							)}%"
						></div>
					</div>
					<p class="text-xs text-slate-400">
						{$_('dragon_store.watches.progress', {
							values: { done: job.progress_done, total: job.progress_total }
						})}
					</p>
				{:else}
					<div class="h-1.5 w-full overflow-hidden rounded bg-slate-200 dark:bg-slate-800">
						<div class="h-full w-1/3 animate-pulse bg-slate-600 dark:bg-slate-300"></div>
					</div>
				{/if}
			</div>
		{/if}
	</form>

	{#if notice}<p class="text-sm text-green-600 dark:text-green-400">{notice}</p>{/if}
	{#if error}<p class="text-sm text-red-500">{error}</p>{/if}

	<!--
		What the add actually took (9.F3). It replaces the dry-run preview removed in 9.X5, and
		says it *after* the fact instead of predicting it: these are the counters the walk wrote
		on the row, so they describe what is in the catalog and not what was expected to be.
	-->
	{#if outcome && outcome.kind === 'category'}
		<div
			class="space-y-2 rounded border border-slate-200 bg-slate-50 p-3 text-sm dark:border-slate-800 dark:bg-slate-900/50"
		>
			<div class="flex items-start justify-between gap-2">
				<p class="font-medium">
					{$_('dragon_store.watches.outcome_title', {
						values: { name: outcome.name ?? outcome.url }
					})}
				</p>
				<button
					type="button"
					class="text-xs text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
					onclick={() => (outcome = null)}
				>
					{$_('dragon_store.watches.outcome_dismiss')}
				</button>
			</div>
			{#if outcome.status === 'ready'}
				<p class="text-slate-600 dark:text-slate-300">
					{$_('dragon_store.watches.outcome_counts', {
						values: { included: outcome.products_included, excluded: outcome.products_excluded }
					})}
				</p>
			{:else if outcome.status === 'cancelled'}
				<p class="text-slate-500">
					{$_('dragon_store.watches.outcome_cancelled', {
						values: { included: outcome.products_included }
					})}
				</p>
			{:else}
				<p class="text-red-500">
					{$_('dragon_store.watches.failed', {
						values: { reason: outcome.status_detail ?? '' }
					})}
				</p>
			{/if}
			<!--
				The resulting list is the catalog: a product carries no link back to the watch that
				brought it in, on purpose — one product can arrive from several categories at once.
			-->
			{#if outcome.products_included > 0}
				<a
					class="inline-block text-indigo-600 hover:underline dark:text-indigo-400"
					href="/catalog"
				>
					{$_('dragon_store.watches.outcome_view')}
				</a>
			{/if}
		</div>
	{/if}

	<!-- Watched products list (3.F3) -->
	<div class="mx-auto w-3/4 space-y-2">
		<h2 class="text-sm font-semibold">{$_('dragon_store.watches.heading')}: {watches.length}</h2>
		{#if watches.length === 0}
			<p class="text-sm text-slate-500">{$_('dragon_store.watches.empty')}</p>
		{:else}
			<table class="w-full text-left text-sm">
				<tbody>
					{#each watches as w (w.id)}
						<tr class="border-b border-slate-100 align-top dark:border-slate-800/60">
							<td class="py-2 pr-4"><ProductThumb src={w.image_url} /></td>
							<td class="py-2 pr-4">
								<div class="mb-1 flex items-center gap-2">
									<span class={kindChip(w.kind)}>
										{w.kind === 'category'
											? $_('dragon_store.watches.kind_category')
											: $_('dragon_store.watches.kind_product')}
									</span>
								</div>
								<ProductCell
									name={w.name ?? w.url}
									url={w.url}
									brand={w.brand}
									category={w.category}
								/>
								<!--
									What this watch last yielded (9.F1). A category is worth a line of its own:
									"a hundred products, twelve dented ones left out" is the only way to tell a
									filter that is doing its job from one that is quietly eating the catalogue.
								-->
								{#if w.kind === 'category'}
									<p class="mt-1 text-xs text-slate-500">
										{#if w.last_scanned_at}
											{$_('dragon_store.watches.scan_counts', {
												values: {
													included: w.products_included,
													excluded: w.products_excluded
												}
											})}
											· {$_('dragon_store.watches.last_scanned', {
												values: { when: dateTime(w.last_scanned_at) }
											})}
										{:else}
											{$_('dragon_store.watches.never_scanned')}
										{/if}
									</p>
								{:else if w.tags.includes(DENTED_TAG)}
									<!--
										Said out loud, because the title does not say it: the sanitiser strips the
										label to keep the catalogue readable, so a dented product you added on
										purpose would otherwise look exactly like the intact one (9.F2).
									-->
									<p class="mt-1 text-xs text-amber-600 dark:text-amber-400">
										{$_('dragon_store.watches.dented_warning')}
									</p>
								{/if}
								<!--
									A watch that could not be read, or that the user stopped, says so on its
									own row: the row exists either way (we keep it, and the next scheduled run
									tries again), so without this it would look like a product that simply has
									no title yet.
								-->
								{#if w.status === 'failed'}
									<p class="mt-1 text-xs text-red-500">
										{$_('dragon_store.watches.failed', {
											values: { reason: w.status_detail ?? '' }
										})}
									</p>
								{:else if w.status === 'cancelled'}
									<p class="mt-1 text-xs text-slate-400">
										{$_('dragon_store.watches.cancelled')}
									</p>
								{/if}
							</td>
							<td class="py-2 pr-4"><ProductTags tags={w.tags} /></td>
							<td class="py-2 pr-4">
								<!--
									Changeable after the fact, because a filter you cannot change is a decision
									you made once with less information than you have now. It applies from the
									next scan: turning it off leaves the dented products already taken where they
									are (the catalogue cleanups of 9.F4 are the tool for those).
								-->
								{#if w.kind === 'category'}
									<label
										class="flex items-center gap-2 text-xs whitespace-nowrap text-slate-600 dark:text-slate-300"
									>
										<input
											type="checkbox"
											checked={w.include_ammaccati}
											disabled={w.status === 'queued' || w.status === 'running'}
											onchange={(e) => setIncludeAmmaccati(w, e.currentTarget.checked)}
										/>
										{$_('dragon_store.watches.include_ammaccati')}
									</label>
								{/if}
							</td>
							<td class="py-2 text-right whitespace-nowrap">
								<button
									class="rounded border border-red-300 px-3 py-1 text-sm text-red-600 transition-colors hover:bg-red-100 dark:border-red-800 dark:text-red-400 dark:hover:bg-red-900/40"
									onclick={() => removeWatch(w.id)}
								>
									{$_('dragon_store.watches.remove')}
								</button>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		{/if}
	</div>

	<!--
		Scrape now (3.F4) — sober: label + caption countdown when on cooldown. Absent from the
		page below super-user (9.F5): not disabled, absent. A disabled button says "you could do
		this, later"; the truth is "this is not yours to do", and the API says the same (9.B8).
	-->
	{#if canScrapeNow}
		<div class="space-y-1">
			<button
				class="inline-flex items-center gap-2 rounded-md bg-emerald-600 px-6 py-3 text-base font-semibold text-white shadow-sm transition-colors hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-50"
				onclick={() => (confirming = true)}
				disabled={locked || busy}
			>
				<span aria-hidden="true" class="text-lg leading-none">⟳</span>
				{$_('dragon_store.scrape_now.action')}
			</button>
			{#if locked}
				<p class="text-xs text-slate-500">
					{$_('dragon_store.scrape_now.cooldown_caption', { values: { time: fmt(remaining) } })}
				</p>
			{/if}
		</div>
	{/if}
</section>

{#if confirming}
	<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
		<div class="w-full max-w-sm space-y-4 rounded-lg bg-white p-5 shadow-lg dark:bg-slate-900">
			<h3 class="text-base font-semibold">{$_('dragon_store.scrape_now.confirm_title')}</h3>
			<p class="text-sm text-slate-500">
				{$_('dragon_store.scrape_now.confirm_body', { values: { interval: intervalLabel } })}
			</p>
			<div class="flex justify-end gap-2">
				<button class={btn} onclick={() => (confirming = false)}>{$_('common.cancel')}</button>
				<button
					class="rounded bg-emerald-600 px-3 py-1 text-sm text-white hover:bg-emerald-500"
					onclick={doScrape}
				>
					{$_('dragon_store.scrape_now.action')}
				</button>
			</div>
		</div>
	</div>
{/if}
