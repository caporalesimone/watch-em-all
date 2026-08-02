<script lang="ts">
	// A scraper's lifetime counters (10.F15), on its admin subpage.
	//
	// **Numbers, not charts.** A cumulative graphed over time is a straight line: it only ever
	// goes up, so a chart of it says nothing a figure does not say better. The trends with an
	// actual time axis are a different block (10.F5) and come from a different table.
	//
	// Three things this panel refuses to show without their caption, each because of a concrete
	// way these numbers get misread: `since` beside the title (a total with no start date means
	// nothing), the failure *streak* ahead of the failure *count* (the question in front of a
	// monitoring page is "is it failing now"), and a note on cache hits, which are pages and not
	// products — one hit can serve fifty items of a category listing.
	import { _ } from 'svelte-i18n';

	import { getLifetimeStats, resetLifetimeStats, type LifetimeStats } from '$lib/api/client';
	import { confirmDialog } from '$lib/stores/confirm';

	let { scraperId }: { scraperId: string } = $props();

	let stats = $state<LifetimeStats | null>(null);
	let loading = $state(true);
	let busy = $state(false);
	let error = $state<string | null>(null);

	$effect(() => {
		const id = scraperId;
		if (id) void load(id);
	});

	async function load(id: string): Promise<void> {
		loading = true;
		error = null;
		try {
			stats = await getLifetimeStats(id);
		} catch {
			error = $_('admin.lifetime.loadError');
		} finally {
			loading = false;
		}
	}

	async function reset(): Promise<void> {
		const ok = await confirmDialog({
			title: $_('admin.lifetime.reset'),
			message: $_('admin.lifetime.confirmReset'),
			confirmLabel: $_('admin.lifetime.reset'),
			danger: true
		});
		if (!ok) return;
		busy = true;
		try {
			stats = await resetLifetimeStats(scraperId);
		} catch {
			error = $_('admin.lifetime.resetError');
		} finally {
			busy = false;
		}
	}

	function when(iso: string | null): string {
		return iso ? new Date(iso).toLocaleString() : '—';
	}

	function bytes(n: number): string {
		if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(1)} GB`;
		if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)} MB`;
		if (n >= 1000) return `${(n / 1000).toFixed(1)} kB`;
		return `${n} B`;
	}

	function duration(seconds: number): string {
		if (seconds >= 3600)
			return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
		if (seconds >= 60) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
		return `${seconds}s`;
	}

	// The four groups, written out as literals so the i18n gate sees every key.
	const groups = $derived(
		stats
			? [
					{
						title: $_('admin.lifetime.groupActivity'),
						rows: [
							{ label: $_('admin.lifetime.runsTotal'), value: String(stats.runs_total) },
							{ label: $_('admin.lifetime.runsOk'), value: String(stats.runs_ok) },
							{ label: $_('admin.lifetime.runsFailed'), value: String(stats.runs_failed) },
							{
								label: $_('admin.lifetime.runsSkipped'),
								value: String(stats.runs_skipped_locked)
							},
							{ label: $_('admin.lifetime.lastRun'), value: when(stats.last_run_at) },
							{ label: $_('admin.lifetime.lastSuccess'), value: when(stats.last_success_at) },
							{ label: $_('admin.lifetime.lastFailure'), value: when(stats.last_failure_at) }
						]
					},
					{
						title: $_('admin.lifetime.groupTraffic'),
						rows: [
							{ label: $_('admin.lifetime.requests'), value: String(stats.http_requests_total) },
							{ label: $_('admin.lifetime.cacheHits'), value: String(stats.cache_hits_total) },
							{ label: $_('admin.lifetime.bytes'), value: bytes(stats.bytes_downloaded_total) },
							{
								label: $_('admin.lifetime.politeness'),
								value: duration(stats.politeness_wait_s_total)
							},
							{ label: $_('admin.lifetime.runTime'), value: duration(stats.run_seconds_total) }
						]
					},
					{
						title: $_('admin.lifetime.groupHealth'),
						rows: [
							{ label: $_('admin.lifetime.rateLimited'), value: String(stats.rate_limited_total) },
							{ label: $_('admin.lifetime.gateHits'), value: String(stats.gate_hits_total) },
							{ label: $_('admin.lifetime.gateCleared'), value: String(stats.gate_cleared_total) },
							{ label: $_('admin.lifetime.robotsDenied'), value: String(stats.robots_denied_total) }
						]
					},
					{
						title: $_('admin.lifetime.groupYield'),
						rows: [
							{
								label: $_('admin.lifetime.delivered'),
								value: String(stats.products_delivered_total)
							},
							{ label: $_('admin.lifetime.pages'), value: String(stats.pages_fetched_total) },
							{
								label: $_('admin.lifetime.parseFailures'),
								value: String(stats.parse_failures_total)
							}
						]
					}
				]
			: []
	);
</script>

<div class="rounded-lg border border-slate-200 p-4 dark:border-slate-800">
	<div class="flex flex-wrap items-baseline justify-between gap-2">
		<h2 class="font-semibold">{$_('admin.lifetime.title')}</h2>
		{#if stats}
			<!-- Beside the title, not in a footnote: a cumulative counter without the date it
			     started from cannot be interpreted at all. -->
			<span class="text-xs text-slate-500">
				{$_('admin.lifetime.since', { values: { date: when(stats.since) } })}
			</span>
		{/if}
	</div>

	{#if loading}
		<p class="mt-3 text-sm text-slate-500">{$_('common.loading')}</p>
	{:else if error && !stats}
		<p class="mt-3 text-sm text-red-500">{error}</p>
	{:else if stats}
		<p class="mt-1 mb-3 text-sm text-slate-500">{$_('admin.lifetime.hint')}</p>

		<!-- Ahead of the four groups, because it is the one number that answers "right now"
		     rather than "ever" — and the one an admin opens this page for. -->
		<div
			class="mb-4 flex items-center justify-between rounded border px-3 py-2 text-sm {stats.consecutive_failures >
			0
				? 'border-red-300 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950/40 dark:text-red-300'
				: 'border-slate-200 text-slate-600 dark:border-slate-800 dark:text-slate-300'}"
		>
			<span>{$_('admin.lifetime.streak')}</span>
			<span class="font-semibold">{stats.consecutive_failures}</span>
		</div>

		<div class="grid gap-4 sm:grid-cols-2">
			{#each groups as g (g.title)}
				<div>
					<h3 class="mb-1 text-xs font-semibold text-slate-400 uppercase">{g.title}</h3>
					<dl class="space-y-1 text-sm">
						{#each g.rows as row (row.label)}
							<div class="flex justify-between gap-4">
								<dt class="text-slate-500">{row.label}</dt>
								<dd class="font-mono">{row.value}</dd>
							</div>
						{/each}
					</dl>
				</div>
			{/each}
		</div>

		<!-- Said where the number appears: a cache hit is a *page* served from the cache, and one
		     category page carries up to fifty products. Read as "requests saved" it would suggest
		     a saving fifty times smaller than the one it represents. -->
		<p class="mt-3 text-xs text-slate-400">{$_('admin.lifetime.cacheNote')}</p>

		<div class="mt-4 flex items-center gap-3">
			<button
				type="button"
				onclick={reset}
				disabled={busy}
				class="rounded border border-red-300 px-3 py-1.5 text-sm text-red-700 hover:bg-red-50 disabled:opacity-50 dark:border-red-800 dark:text-red-400 dark:hover:bg-red-950"
			>
				{$_('admin.lifetime.reset')}
			</button>
			{#if error}<span class="text-sm text-red-500">{error}</span>{/if}
		</div>
	{/if}
</div>
