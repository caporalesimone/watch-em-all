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
	const SIZES = [25, 50, 100];
	const MAX_LIVE = 500; // cap rows kept while tailing

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

	let liveTimer: ReturnType<typeof setInterval> | undefined;
	let searchTimer: ReturnType<typeof setTimeout> | undefined;

	const pages = $derived(Math.max(1, Math.ceil(total / size)));
	const fromIdx = $derived(total === 0 ? 0 : (page - 1) * size + 1);
	const toIdx = $derived(Math.min(page * size, total));

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

	async function pollLive(): Promise<void> {
		try {
			const fresh = await tailLogs({ ...filters(), since: maxId(), limit: 200 });
			if (fresh.length === 0) return;
			// tail returns ascending; show newest first and keep counts/total in sync client-side.
			for (const r of fresh) {
				if (r.level in counts) counts = { ...counts, [r.level]: counts[r.level] + 1 };
				if (!allSources.includes(r.source)) allSources = [...allSources, r.source].sort();
			}
			total += fresh.length;
			entries = [...[...fresh].reverse(), ...entries].slice(0, MAX_LIVE);
		} catch {
			/* transient: keep the current view, try again next tick */
		}
	}

	function stopLive(): void {
		if (liveTimer) clearInterval(liveTimer);
		liveTimer = undefined;
	}

	function setLive(on: boolean): void {
		live = on;
		stopLive();
		page = 1;
		if (on) {
			void loadPage(); // seed latest page + stats, then tail from its max id
			liveTimer = setInterval(pollLive, 5000);
		} else {
			void loadPage();
		}
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
	function fmtTime(iso: string): string {
		const d = new Date(iso);
		const p = (n: number, l = 2) => String(n).padStart(l, '0');
		return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}.${p(d.getMilliseconds(), 3)}`;
	}

	const SOURCE_DOT: Record<string, string> = {
		scraper: 'bg-emerald-500',
		worker: 'bg-sky-500',
		notifier: 'bg-violet-500',
		api: 'bg-teal-500',
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
				<span class="h-2 w-2 rounded-full {live ? 'bg-emerald-500' : 'bg-slate-400'}"></span>
				{$_('admin.logs.live')}
			</button>
			<button
				type="button"
				class="rounded border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800"
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
			class="min-w-64 flex-1 rounded border border-slate-300 bg-white px-3 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900"
		/>
		<div class="flex items-center gap-1">
			<button type="button" class={tabClass(level === null)} onclick={() => setLevel(null)}>
				{$_('admin.logs.all')} <span class="opacity-60">{total}</span>
			</button>
			{#each ['info', 'warning', 'error'] as const as lv (lv)}
				<button type="button" class={tabClass(level === lv)} onclick={() => setLevel(lv)}>
					{LEVEL_LABEL[lv]} <span class="opacity-60">{counts[lv] ?? 0}</span>
				</button>
			{/each}
		</div>
		<select
			value={size}
			onchange={(e) => setSize(Number(e.currentTarget.value))}
			class="rounded border border-slate-300 bg-white px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900"
		>
			{#each SIZES as n (n)}
				<option value={n}>{$_('admin.logs.perPage', { values: { n } })}</option>
			{/each}
		</select>
	</div>

	<!-- source chips -->
	{#if allSources.length > 0}
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
	{/if}

	{#if loading && entries.length === 0}
		<p class="text-sm text-slate-500">{$_('common.loading')}</p>
	{:else if error}
		<p class="text-sm text-red-500">{error}</p>
	{:else if entries.length === 0}
		<p class="text-sm text-slate-500">{$_('admin.logs.empty')}</p>
	{:else}
		<table class="w-full text-left text-sm">
			<thead class="border-b border-slate-200 text-xs text-slate-500 dark:border-slate-800">
				<tr>
					<th class="py-2 pr-4">{$_('admin.logs.colTime')}</th>
					<th class="py-2 pr-4">{$_('admin.logs.colSource')}</th>
					<th class="py-2 pr-4">{$_('admin.logs.colLevel')}</th>
					<th class="py-2 pr-4">{$_('admin.logs.colMessage')}</th>
					<th class="py-2"></th>
				</tr>
			</thead>
			<tbody>
				{#each entries as e (e.id)}
					<tr class="border-b border-slate-100 dark:border-slate-800/60">
						<td class="py-1.5 pr-4 font-mono text-xs whitespace-nowrap text-slate-500"
							>{fmtTime(e.created_at)}</td
						>
						<td class="py-1.5 pr-4">
							<span class="inline-flex items-center gap-1.5">
								<span class="h-2 w-2 rounded-full {sourceDot(e.source)}"></span>
								<span class="text-xs">{e.source}</span>
							</span>
						</td>
						<td class="py-1.5 pr-4">
							<span class="rounded px-1.5 py-0.5 font-mono text-[11px] {LEVEL_BADGE[e.level]}">
								{LEVEL_LABEL[e.level]}
							</span>
						</td>
						<td class="py-1.5 pr-4 font-mono text-xs">{e.message}</td>
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
				<div class="flex items-center gap-1">
					<button
						type="button"
						class="rounded px-2 py-1 hover:bg-slate-100 disabled:opacity-40 dark:hover:bg-slate-800"
						onclick={() => goTo(page - 1)}
						disabled={page <= 1}>‹</button
					>
					<span class="px-2 font-mono">{page} / {pages}</span>
					<button
						type="button"
						class="rounded px-2 py-1 hover:bg-slate-100 disabled:opacity-40 dark:hover:bg-slate-800"
						onclick={() => goTo(page + 1)}
						disabled={page >= pages}>›</button
					>
				</div>
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
