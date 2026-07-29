<script lang="ts">
	import { onDestroy, onMount } from 'svelte';

	import { apiFetch } from '$lib/auth/manager';
	import ProductCell from '$lib/components/ProductCell.svelte';
	import ProductTags from '$lib/components/ProductTags.svelte';
	import ProductThumb from '$lib/components/ProductThumb.svelte';
	import { _ } from '$lib/i18n';

	const BASE = '/api/plugins/dragon-store';

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

	let watches = $state<Watch[]>([]);
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
			job = next.active ? next : null;
			if (finished) await loadWatches(); // it landed: show the resolved row
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
		void loadStatus();
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
		stopJobPolling();
	});

	async function addWatch(event: Event): Promise<void> {
		event.preventDefault();
		error = null;
		notice = null;
		if (!url.trim()) {
			error = $_('dragon_store.watches.invalid');
			return;
		}
		// Adding a watch scrapes the product there and then, and the site's own Crawl-delay
		// makes that take tens of seconds — plus the anti-bot gate, which costs two extra
		// waits. Without `busy` the form looked inert for all that time and could be
		// submitted twice. The notice states the wait and nothing else: why it is slow is
		// our problem, not something the user can act on.
		busy = true;
		try {
			const res = await apiFetch(`${BASE}/watches`, {
				method: 'POST',
				headers: { 'content-type': 'application/json' },
				body: JSON.stringify({ url: url.trim() })
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
							: code === 'unsupported_url'
								? 'dragon_store.watches.unsupported'
								: code === 'invalid_url'
									? 'dragon_store.watches.invalid_url'
									: 'dragon_store.error'
				);
				return;
			}
			url = '';
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
			/>
			<button
				type="submit"
				class="rounded bg-slate-800 px-3 py-1 text-sm text-white hover:bg-slate-700 disabled:opacity-50 dark:bg-slate-200 dark:text-slate-900 dark:hover:bg-white"
				disabled={busy}
			>
				{$_('dragon_store.watches.add')}
			</button>
		</div>
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
								<ProductCell
									name={w.name ?? w.url}
									url={w.url}
									brand={w.brand}
									category={w.category}
								/>
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

	<!-- Scrape now (3.F4) — sober: label + caption countdown when on cooldown -->
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
