<script lang="ts">
	// System logs (4.F3/4.F4). Hybrid: Live ON tails the cursor (auto-refresh, pagination
	// off); Live OFF browses history by page number (offset + total + per-level counts).
	// Filters: level tabs (with counts), multi-source chips, and a debounced message search.
	// A row's { } opens its context JSON. Levels are info/warning/error; sources are dynamic.
	import { onMount } from 'svelte';
	import { _ } from 'svelte-i18n';

	import { getLogsPage, tailLogs, type SystemLogEntry, type LogQuery } from '$lib/api/client';
	import PageTitle from '$lib/components/PageTitle.svelte';

	type Level = 'info' | 'warning' | 'error';
	const SIZES = [50, 100, 200];
	const MAX_LIVE = 500; // cap rows kept while tailing
	// How often the tail asks for new rows. Only `system_log` sources write here (worker,
	// scraper, notifier, alert), so between scheduled runs there is genuinely nothing new —
	// which is why the dot below blinks on every poll: "quiet" must look different from "stuck".
	const LIVE_INTERVALS_S = [1, 5, 10];
	const DEFAULT_LIVE_INTERVAL_S = 5;
	const BLINK_MS = 350;

	let entries = $state<SystemLogEntry[]>([]);
	let total = $state(0);
	let counts = $state<Record<string, number>>({ info: 0, warning: 0, error: 0 });
	let allSources = $state<string[]>([]);

	let live = $state(false);
	let level = $state<Level | null>(null);
	let selectedSources = $state<string[]>([]);
	let q = $state('');
	let page = $state(1);
	let size = $state(50);

	let loading = $state(true);
	let error = $state<string | null>(null);
	let contextRow = $state<SystemLogEntry | null>(null);

	let liveIntervalS = $state(DEFAULT_LIVE_INTERVAL_S);
	let polling = $state(false); // drives the dot's blink: one flash per request
	let tailError = $state<string | null>(null);

	let liveTimer: ReturnType<typeof setInterval> | undefined;
	let searchTimer: ReturnType<typeof setTimeout> | undefined;
	let blinkTimer: ReturnType<typeof setTimeout> | undefined;

	const pages = $derived(Math.max(1, Math.ceil(total / size)));
	const fromIdx = $derived(total === 0 ? 0 : (page - 1) * size + 1);
	const toIdx = $derived(Math.min(page * size, total));

	// A sliding window of at most 5 page numbers, centred on the current page.
	function pageNumbers(): number[] {
		const span = 2;
		let start = Math.max(1, page - span);
		const end = Math.min(pages, start + 2 * span);
		start = Math.max(1, end - 2 * span);
		const out: number[] = [];
		for (let p = start; p <= end; p++) out.push(p);
		return out;
	}

	function filters(): LogQuery {
		return { level, sources: selectedSources, q: q.trim() || undefined };
	}

	async function loadPage(): Promise<void> {
		loading = true;
		error = null;
		try {
			const res = await getLogsPage({ ...filters(), page, size });
			entries = res.items;
			total = res.total;
			counts = res.counts;
			allSources = res.sources;
		} catch {
			error = $_('admin.logs.loadError');
		} finally {
			loading = false;
		}
	}

	function maxId(): number {
		return entries.reduce((m, e) => Math.max(m, e.id), 0);
	}

	function blink(): void {
		polling = true;
		if (blinkTimer) clearTimeout(blinkTimer);
		blinkTimer = setTimeout(() => (polling = false), BLINK_MS);
	}

	async function pollLive(): Promise<void> {
		blink(); // one flash per request, so an idle tail still looks alive
		try {
			const fresh = await tailLogs({ ...filters(), since: maxId(), limit: 200 });
			tailError = null;
			if (fresh.length === 0) return;
			// tail returns ascending; show newest first and keep counts/total in sync client-side.
			for (const r of fresh) {
				if (r.level in counts) counts = { ...counts, [r.level]: counts[r.level] + 1 };
				if (!allSources.includes(r.source)) allSources = [...allSources, r.source].sort();
			}
			total += fresh.length;
			entries = [...[...fresh].reverse(), ...entries].slice(0, MAX_LIVE);
		} catch (err) {
			// Transient: keep the current view and try again next tick — but say so. Swallowing
			// this silently made a broken tail indistinguishable from a quiet one.
			tailError = err instanceof Error ? err.message : String(err);
			console.error('log tail failed', err);
		}
	}

	function stopLive(): void {
		if (liveTimer) clearInterval(liveTimer);
		liveTimer = undefined;
		if (blinkTimer) clearTimeout(blinkTimer);
		blinkTimer = undefined;
		polling = false;
	}

	function setLive(on: boolean): void {
		live = on;
		stopLive();
		page = 1;
		tailError = null;
		if (on) {
			void loadPage(); // seed latest page + stats, then tail from its max id
			liveTimer = setInterval(pollLive, liveIntervalS * 1000);
		} else {
			void loadPage();
		}
	}

	function setLiveInterval(seconds: number): void {
		liveIntervalS = seconds;
		if (!live) return;
		// Restart the timer so the new cadence applies now, not after the pending tick.
		if (liveTimer) clearInterval(liveTimer);
		liveTimer = setInterval(pollLive, seconds * 1000);
	}

	// Re-query after a filter/size/page change (live re-seeds, history reloads the page).
	function applyChange(resetPage = true): void {
		if (resetPage) page = 1;
		void loadPage();
	}

	function onSearchInput(value: string): void {
		q = value;
		if (searchTimer) clearTimeout(searchTimer);
		searchTimer = setTimeout(() => applyChange(), 300);
	}

	function setLevel(l: Level | null): void {
		level = l;
		applyChange();
	}

	function toggleSource(s: string): void {
		selectedSources = selectedSources.includes(s)
			? selectedSources.filter((x) => x !== s)
			: [...selectedSources, s];
		applyChange();
	}

	function setSize(n: number): void {
		size = n;
		applyChange();
	}

	function goTo(p: number): void {
		if (p < 1 || p > pages || p === page) return;
		page = p;
		void loadPage();
	}

	onMount(() => {
		void loadPage();
		return () => {
			stopLive();
			if (searchTimer) clearTimeout(searchTimer);
		};
	});

	// --- presentation helpers ---
	const pad = (n: number, l = 2) => String(n).padStart(l, '0');

	/** ISO 8601 date, in the reader's own timezone so it matches the time beside it. */
	function fmtDate(iso: string): string {
		const d = new Date(iso);
		return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
	}

	function fmtTime(iso: string): string {
		const d = new Date(iso);
		return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.${pad(d.getMilliseconds(), 3)}`;
	}

	const SOURCE_DOT: Record<string, string> = {
		scraper: 'bg-emerald-500',
		worker: 'bg-sky-500',
		web: 'bg-teal-500',
		notifier: 'bg-violet-500',
		alert: 'bg-amber-500',
		db: 'bg-pink-500'
	};
	function sourceDot(s: string): string {
		return SOURCE_DOT[s] ?? 'bg-slate-400';
	}

	const LEVEL_BADGE: Record<Level, string> = {
		error: 'bg-red-500/15 text-red-600 dark:text-red-300',
		warning: 'bg-amber-500/15 text-amber-600 dark:text-amber-300',
		info: 'bg-slate-500/15 text-slate-600 dark:text-slate-300'
	};
	const LEVEL_LABEL: Record<Level, string> = { info: 'INFO', warning: 'WARN', error: 'ERR' };

	const tabClass = (active: boolean) =>
		`rounded px-2.5 py-1 text-xs font-medium ${
			active
				? 'bg-slate-200 text-slate-900 dark:bg-slate-700 dark:text-white'
				: 'text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800'
		}`;
</script>

<section class="space-y-5">
	<div class="flex flex-wrap items-start justify-between gap-3">
		<div>
			<PageTitle title={$_('admin.logs.title')} />
			<p class="text-sm text-slate-500">{$_('admin.logs.subtitle')}</p>
		</div>
		<div class="flex items-center gap-2">
			<button
				type="button"
				class="flex items-center gap-2 rounded border px-3 py-1.5 text-sm {live
					? 'border-emerald-500/40 text-emerald-600 dark:text-emerald-400'
					: 'border-slate-300 text-slate-500 dark:border-slate-700'}"
				onclick={() => setLive(!live)}
			>
				<span
					class="h-2 w-2 rounded-full transition-opacity duration-150 {live
						? 'bg-emerald-500'
						: 'bg-slate-400'} {live && polling ? 'opacity-30' : 'opacity-100'}"
				></span>
				{$_('admin.logs.live')}
			</button>
			{#if live}
				<!-- Cadence of the tail. Only shown while tailing: it means nothing otherwise. -->
				<div class="flex items-center gap-1">
					{#each LIVE_INTERVALS_S as s (s)}
						<button
							type="button"
							class={tabClass(liveIntervalS === s)}
							onclick={() => setLiveInterval(s)}>{s}s</button
						>
					{/each}
				</div>
			{/if}
			<!-- Greyed rather than hidden while tailing: the tail already refreshes, and removing
			     the button would shuffle the toolbar every time Live is toggled. -->
			<button
				type="button"
				class="rounded border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent dark:border-slate-700 dark:hover:bg-slate-800 dark:disabled:hover:bg-transparent"
				disabled={live}
				title={live ? $_('admin.logs.disabledInLive') : undefined}
				onclick={() => loadPage()}
			>
				↻ {$_('admin.logs.refresh')}
			</button>
		</div>
	</div>

	<!-- search + level tabs + page size -->
	<div class="flex flex-wrap items-center gap-3">
		<input
			type="search"
			placeholder={$_('admin.logs.search')}
			value={q}
			oninput={(e) => onSearchInput(e.currentTarget.value)}
			class="w-full rounded border border-slate-300 bg-white px-3 py-1.5 text-sm sm:w-96 dark:border-slate-700 dark:bg-slate-900"
		/>
		<!-- Fixed-width search, not flex-1: the level tabs change width when the counts change
		     (and when the active one gains its background), and a flex-1 input absorbed that
		     difference — so picking a filter visibly resized the search box. -->
		<div class="flex shrink-0 items-center gap-1">
			<button type="button" class={tabClass(level === null)} onclick={() => setLevel(null)}>
				{$_('admin.logs.all')} <span class="tabular-nums opacity-60">{total}</span>
			</button>
			{#each ['info', 'warning', 'error'] as const as lv (lv)}
				<button type="button" class={tabClass(level === lv)} onclick={() => setLevel(lv)}>
					{LEVEL_LABEL[lv]} <span class="tabular-nums opacity-60">{counts[lv] ?? 0}</span>
				</button>
			{/each}
		</div>
		<!-- Rows per page only governs the paged history; while tailing there are no pages. -->
		<select
			value={size}
			disabled={live}
			title={live ? $_('admin.logs.disabledInLive') : undefined}
			onchange={(e) => setSize(Number(e.currentTarget.value))}
			class="rounded border border-slate-300 bg-white px-2 py-1.5 text-sm disabled:cursor-not-allowed disabled:opacity-40 sm:ml-auto dark:border-slate-700 dark:bg-slate-900"
		>
			{#each SIZES as n (n)}
				<option value={n}>{$_('admin.logs.perPage', { values: { n } })}</option>
			{/each}
		</select>
	</div>

	{#snippet pager()}
		<div class="flex items-center gap-1">
			<button
				type="button"
				class="rounded px-2 py-1 text-sm hover:bg-slate-100 disabled:opacity-40 dark:hover:bg-slate-800"
				onclick={() => goTo(page - 1)}
				disabled={page <= 1}>‹</button
			>
			{#each pageNumbers() as p (p)}
				<button type="button" class={tabClass(p === page)} onclick={() => goTo(p)}>{p}</button>
			{/each}
			<button
				type="button"
				class="rounded px-2 py-1 text-sm hover:bg-slate-100 disabled:opacity-40 dark:hover:bg-slate-800"
				onclick={() => goTo(page + 1)}
				disabled={page >= pages}>›</button
			>
		</div>
	{/snippet}

	<!-- source chips (left) + pager (right) on one row, so the table sits right under it -->
	{#if allSources.length > 0}
		<div class="flex flex-wrap items-center justify-between gap-2">
			<div class="flex flex-wrap items-center gap-2">
				<span class="text-xs font-semibold tracking-wide text-slate-400 uppercase">
					{$_('admin.logs.sources')}
				</span>
				{#each allSources as s (s)}
					<button
						type="button"
						class="flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs {selectedSources.includes(
							s
						)
							? 'border-slate-400 bg-slate-100 dark:border-slate-500 dark:bg-slate-800'
							: 'border-slate-200 text-slate-500 dark:border-slate-800'}"
						onclick={() => toggleSource(s)}
					>
						<span class="h-2 w-2 rounded-full {sourceDot(s)}"></span>{s}
					</button>
				{/each}
			</div>
			{#if !live && total > 0}
				{@render pager()}
			{/if}
		</div>
	{/if}

	{#if tailError}
		<p class="text-sm text-amber-600 dark:text-amber-400">
			{$_('admin.logs.tailError', { values: { error: tailError } })}
		</p>
	{/if}

	{#if loading && entries.length === 0}
		<p class="text-sm text-slate-500">{$_('common.loading')}</p>
	{:else if error}
		<p class="text-sm text-red-500">{error}</p>
	{:else if entries.length === 0}
		<p class="text-sm text-slate-500">{$_('admin.logs.empty')}</p>
	{:else}
		<!-- Fixed layout: column widths stay put regardless of content/filter (Message takes the rest). -->
		<table class="w-full table-fixed text-left text-sm">
			<colgroup>
				<col style="width: 7rem" />
				<col style="width: 7rem" />
				<col style="width: 6rem" />
				<col style="width: 5rem" />
				<col />
				<col style="width: 3rem" />
			</colgroup>
			<thead class="border-b border-slate-200 text-xs text-slate-500 dark:border-slate-800">
				<tr>
					<th class="py-2 text-center">{$_('admin.logs.colDate')}</th>
					<th class="py-2 text-center">{$_('admin.logs.colTime')}</th>
					<th class="py-2 text-center">{$_('admin.logs.colSource')}</th>
					<th class="py-2 text-center">{$_('admin.logs.colLevel')}</th>
					<th class="py-2 pr-4">{$_('admin.logs.colMessage')}</th>
					<th class="py-2"></th>
				</tr>
			</thead>
			<tbody>
				{#each entries as e (e.id)}
					<tr class="border-b border-slate-100 dark:border-slate-800/60">
						<td class="py-1.5 text-center font-mono text-xs whitespace-nowrap text-slate-500"
							>{fmtDate(e.created_at)}</td
						>
						<td class="py-1.5 text-center font-mono text-xs whitespace-nowrap text-slate-500"
							>{fmtTime(e.created_at)}</td
						>
						<td class="py-1.5 text-center">
							<span class="inline-flex items-center gap-1.5">
								<span class="h-2 w-2 rounded-full {sourceDot(e.source)}"></span>
								<span class="text-xs">{e.source}</span>
							</span>
						</td>
						<td class="py-1.5 text-center">
							<span class="rounded px-1.5 py-0.5 font-mono text-[11px] {LEVEL_BADGE[e.level]}">
								{LEVEL_LABEL[e.level]}
							</span>
						</td>
						<td class="py-1.5 pr-4 font-mono text-xs break-words">{e.message}</td>
						<td class="py-1.5 text-right">
							{#if e.context}
								<button
									type="button"
									class="rounded px-1.5 font-mono text-xs text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-200"
									title={$_('admin.logs.context')}
									onclick={() => (contextRow = e)}>{'{ }'}</button
								>
							{/if}
						</td>
					</tr>
				{/each}
			</tbody>
		</table>

		<!-- pagination only when not tailing -->
		{#if !live}
			<div class="flex flex-wrap items-center justify-between gap-3 pt-1 text-sm text-slate-500">
				<span>{$_('admin.logs.showing', { values: { from: fromIdx, to: toIdx, total } })}</span>
				{@render pager()}
			</div>
		{/if}
	{/if}
</section>

{#if contextRow}
	<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
		<div
			class="max-h-[80vh] w-full max-w-lg overflow-auto rounded-lg border border-slate-200 bg-white p-5 shadow-xl dark:border-slate-700 dark:bg-slate-900"
			role="dialog"
			aria-modal="true"
		>
			<div class="mb-3 flex items-center justify-between">
				<h2 class="font-semibold">{$_('admin.logs.context')}</h2>
				<button
					type="button"
					class="rounded px-2 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
					aria-label={$_('common.cancel')}
					onclick={() => (contextRow = null)}>✕</button
				>
			</div>
			<pre
				class="overflow-auto rounded bg-slate-100 p-3 font-mono text-xs dark:bg-slate-800">{JSON.stringify(
					contextRow.context,
					null,
					2
				)}</pre>
		</div>
	</div>
{/if}
