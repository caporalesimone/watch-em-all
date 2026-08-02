<script lang="ts">
	// Run monitoring (10.F3). Deliberately a *recent window*: these rows are pruned by the
	// nightly maintenance, and the page says so rather than letting an empty older page read
	// as "nothing ever ran".
	import { onMount } from 'svelte';
	import { _ } from 'svelte-i18n';

	import { getRunDetail, listRuns, type RunSummary, type RunUserDetail } from '$lib/api/client';
	import PageTitle from '$lib/components/PageTitle.svelte';

	let runs = $state<RunSummary[]>([]);
	let total = $state(0);
	let page = $state(1);
	let statusFilter = $state<string | null>(null);
	let loading = $state(true);

	const PAGE_SIZE = 25;
	const pages = $derived(Math.max(1, Math.ceil(total / PAGE_SIZE)));

	async function refresh(): Promise<void> {
		const result = await listRuns({ status: statusFilter, page, pageSize: PAGE_SIZE });
		runs = result.items;
		total = result.total;
		loading = false;
	}

	onMount(() => void refresh());

	function setStatus(next: string | null): void {
		statusFilter = next;
		page = 1; // a filtered set is shorter, and page 7 of it may not exist
		void refresh();
	}

	function go(delta: number): void {
		page = Math.min(pages, Math.max(1, page + delta));
		void refresh();
	}

	// Written out rather than built from the value, so the i18n gate can see every key.
	const outcomes = $derived([
		{ key: null, label: $_('admin.runs.filterAll') },
		{ key: 'ok', label: $_('admin.runs.statusOk') },
		{ key: 'partial', label: $_('admin.runs.statusPartial') },
		{ key: 'error', label: $_('admin.runs.statusError') },
		{ key: 'timeout', label: $_('admin.runs.statusTimeout') }
	]);

	function outcomeLabel(status: string): string {
		return outcomes.find((o) => o.key === status)?.label ?? status;
	}

	// Colour carries the same information as the word, for the scan down the column.
	const TONE: Record<string, string> = {
		ok: 'text-green-600 dark:text-green-400',
		partial: 'text-amber-600 dark:text-amber-400',
		error: 'text-red-600 dark:text-red-400',
		timeout: 'text-red-600 dark:text-red-400'
	};

	function duration(run: RunSummary): string {
		if (!run.finished_at) return '—'; // still running, or died without closing its row
		const ms = new Date(run.finished_at).getTime() - new Date(run.started_at).getTime();
		return ms < 1000 ? '<1s' : `${Math.round(ms / 1000)}s`;
	}

	// --- drill-down (10.F4) --------------------------------------------------------------
	// Expanded inline under its own row rather than on a separate page: the question it
	// answers ("which user did this run fail for") is only ever asked while looking at the
	// run, and a navigation away would lose the filter and the page you were on.
	let openRunId = $state<number | null>(null);
	let detail = $state<RunUserDetail[]>([]);
	let detailLoading = $state(false);

	async function toggleDetail(runId: number): Promise<void> {
		if (openRunId === runId) {
			openRunId = null;
			return;
		}
		openRunId = runId;
		detail = [];
		detailLoading = true;
		try {
			detail = await getRunDetail(runId);
		} finally {
			detailLoading = false;
		}
	}

	const th = 'py-2 pr-4';
</script>

<section class="space-y-4">
	<PageTitle title={$_('admin.runs.title')} />
	<p class="text-sm text-slate-500">{$_('admin.runs.hint')}</p>

	<div class="flex flex-wrap gap-2 text-xs">
		{#each outcomes as chip (chip.label)}
			<button
				type="button"
				onclick={() => setStatus(chip.key)}
				class="rounded-full border px-3 py-1 {statusFilter === chip.key
					? 'border-slate-800 bg-slate-800 text-white dark:border-slate-200 dark:bg-slate-200 dark:text-slate-900'
					: 'border-slate-300 hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800'}"
			>
				{chip.label}
			</button>
		{/each}
	</div>

	{#if loading}
		<p class="text-sm text-slate-500">{$_('common.loading')}</p>
	{:else if runs.length === 0}
		<p class="text-sm text-slate-500">{$_('admin.runs.empty')}</p>
	{:else}
		<table class="w-full text-left text-sm">
			<thead class="border-b border-slate-200 text-xs text-slate-500 dark:border-slate-800">
				<tr>
					<th class={th}>{$_('admin.runs.colWhen')}</th>
					<th class={th}>{$_('admin.runs.colScraper')}</th>
					<th class={th}>{$_('admin.runs.colTrigger')}</th>
					<th class={th}>{$_('admin.runs.colStatus')}</th>
					<th class={th}>{$_('admin.runs.colDuration')}</th>
					<th class={th}>{$_('admin.runs.colUsers')}</th>
					<th class={th}>{$_('admin.runs.colFound')}</th>
					<th class={th}>{$_('admin.runs.colNew')}</th>
					<th class={th}>{$_('admin.runs.colChanges')}</th>
					<th class={th}>{$_('admin.runs.colRequests')}</th>
					<th class={th}>{$_('admin.runs.colCache')}</th>
				</tr>
			</thead>
			<tbody>
				{#each runs as run (run.run_id)}
					<tr
						class="cursor-pointer border-b border-slate-100 hover:bg-slate-50 dark:border-slate-800/60 dark:hover:bg-slate-800/40"
						onclick={() => toggleDetail(run.run_id)}
					>
						<td class={th}>{new Date(run.started_at).toLocaleString()}</td>
						<td class={th}>{run.scraper_id}</td>
						<td class="{th} text-slate-500">{run.trigger}</td>
						<td class="{th} {TONE[run.status] ?? ''}">{outcomeLabel(run.status)}</td>
						<td class="{th} text-slate-500">{duration(run)}</td>
						<td class={th}>{run.users_processed}</td>
						<td class={th}>{run.products_found}</td>
						<td class={th}>{run.products_new}</td>
						<td class={th}>{run.price_changes}</td>
						<td class={th}>{run.http_requests}</td>
						<td class={th}>{run.cache_hits}</td>
					</tr>
					{#if openRunId === run.run_id}
						<tr class="border-b border-slate-100 dark:border-slate-800/60">
							<td colspan="11" class="bg-slate-50 px-3 py-3 dark:bg-slate-800/40">
								<p class="mb-2 text-xs font-medium text-slate-500">
									{$_('admin.runs.detailTitle')}
								</p>
								{#if detailLoading}
									<p class="text-xs text-slate-500">{$_('common.loading')}</p>
								{:else}
									<table class="w-full text-left text-xs">
										<thead class="text-slate-500">
											<tr>
												<th class="py-1 pr-4">{$_('admin.runs.colUser')}</th>
												<th class="py-1 pr-4">{$_('admin.runs.colStatus')}</th>
												<th class="py-1 pr-4">{$_('admin.runs.colFound')}</th>
												<th class="py-1 pr-4">{$_('admin.runs.colNew')}</th>
												<th class="py-1 pr-4">{$_('admin.runs.colChanges')}</th>
												<th class="py-1 pr-4">{$_('admin.runs.colRequests')}</th>
												<th class="py-1 pr-4">{$_('admin.runs.colCache')}</th>
												<th class="py-1 pr-4">{$_('admin.runs.colError')}</th>
											</tr>
										</thead>
										<tbody>
											{#each detail as row (row.user_id)}
												<tr>
													<!--
														A purged account leaves its rows behind, so the name can be
														null. Saying so is better than an empty cell, which reads as
														a bug rather than as history.
													-->
													<td class="py-1 pr-4">{row.username ?? $_('admin.runs.deletedUser')}</td>
													<td class="py-1 pr-4 {TONE[row.status] ?? ''}"
														>{outcomeLabel(row.status)}</td
													>
													<td class="py-1 pr-4">{row.products_found}</td>
													<td class="py-1 pr-4">{row.products_new}</td>
													<td class="py-1 pr-4">{row.price_changes}</td>
													<td class="py-1 pr-4">{row.http_requests}</td>
													<td class="py-1 pr-4">{row.cache_hits}</td>
													<td class="py-1 pr-4 text-red-600 dark:text-red-400"
														>{row.error_message ?? ''}</td
													>
												</tr>
											{/each}
										</tbody>
									</table>
								{/if}
								<button
									type="button"
									class="mt-2 text-xs text-slate-500 underline"
									onclick={() => (openRunId = null)}>{$_('admin.runs.close')}</button
								>
							</td>
						</tr>
					{/if}
				{/each}
			</tbody>
		</table>

		{#if pages > 1}
			<div class="flex items-center gap-3 text-xs text-slate-500">
				<button
					type="button"
					class="rounded border border-slate-300 px-2 py-1 disabled:opacity-40 dark:border-slate-700"
					disabled={page <= 1}
					onclick={() => go(-1)}>{$_('admin.runs.prev')}</button
				>
				<span>{page} / {pages}</span>
				<button
					type="button"
					class="rounded border border-slate-300 px-2 py-1 disabled:opacity-40 dark:border-slate-700"
					disabled={page >= pages}
					onclick={() => go(1)}>{$_('admin.runs.next')}</button
				>
			</div>
		{/if}
	{/if}
</section>
