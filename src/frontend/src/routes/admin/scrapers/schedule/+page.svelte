<script lang="ts">
	// Admin schedule editor (4.F1): one row per scraper — its daily times as removable
	// HH:MM:SS chips, plus a time picker to add one and an Active toggle. Adding is blocked
	// in the UI when the time falls within 1 minute of ANY scraper's time (serial runner).
	// Non-schedulable plugins (stubs) show as such and can't be scheduled. The 24-hour
	// visualization is added below in a later step (4.F1b).
	import { onMount } from 'svelte';
	import { _ } from 'svelte-i18n';

	import {
		getPlugins,
		listScrapers,
		updateScraperSchedule,
		type PluginInfo,
		type ScraperListItem
	} from '$lib/api/client';
	import PageTitle from '$lib/components/PageTitle.svelte';
	import ScheduleTimeline from '$lib/components/ScheduleTimeline.svelte';

	type Row = {
		id: string;
		name: string;
		icon: string | null;
		schedulable: boolean;
		times: string[]; // canonical HH:MM:SS from the API
		enabled: boolean;
		addValue: string; // the row's time-picker value
	};

	let rows = $state<Row[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let saving = $state(false);

	onMount(async () => {
		try {
			const [plugins, scrapers] = await Promise.all([getPlugins(), listScrapers()]);
			const byId = new Map<string, ScraperListItem>(scrapers.map((s) => [s.scraper_id, s]));
			rows = plugins
				.filter((p: PluginInfo) => p.type === 'scraper')
				.map((p: PluginInfo) => {
					const s = byId.get(p.name);
					return {
						id: p.name,
						name: p.display_name,
						icon: p.icon,
						schedulable: s !== undefined,
						times: s ? s.times : [],
						enabled: s ? s.enabled : true,
						addValue: ''
					};
				});
		} catch {
			error = $_('admin.scrapers.loadError');
		} finally {
			loading = false;
		}
	});

	function timeToSeconds(v: string): number | null {
		const m = /^(\d{1,2}):(\d{2})(?::(\d{2}))?$/.exec(v);
		if (!m) return null;
		const h = +m[1];
		const min = +m[2];
		const s = m[3] ? +m[3] : 0;
		if (h > 23 || min > 59 || s > 59) return null;
		return h * 3600 + min * 60 + s;
	}

	function toHHMMSS(v: string): string {
		const sec = timeToSeconds(v) ?? 0;
		const pad = (n: number) => String(n).padStart(2, '0');
		return `${pad(Math.floor(sec / 3600))}:${pad(Math.floor((sec % 3600) / 60))}:${pad(sec % 60)}`;
	}

	// Circular distance (seconds) on a 24h clock, so 23:59:40 and 00:00:10 count as 30s apart.
	function gap(a: number, b: number): number {
		const d = Math.abs(a - b);
		return Math.min(d, 86400 - d);
	}

	// Global rule: the candidate may not be within 1 minute of ANY scraper's time.
	function tooClose(row: Row): boolean {
		const c = row.addValue ? timeToSeconds(row.addValue) : null;
		if (c === null) return false;
		for (const r of rows) {
			if (!r.schedulable) continue;
			for (const t of r.times) {
				const ts = timeToSeconds(t);
				if (ts !== null && gap(c, ts) < 60) return true;
			}
		}
		return false;
	}

	function canAdd(row: Row): boolean {
		return (
			row.schedulable &&
			!saving &&
			row.addValue !== '' &&
			timeToSeconds(row.addValue) !== null &&
			!tooClose(row)
		);
	}

	async function persist(row: Row, times: string[], enabled: boolean): Promise<void> {
		saving = true;
		error = null;
		try {
			const updated = await updateScraperSchedule(row.id, { times, enabled });
			row.times = updated.times;
			row.enabled = updated.enabled;
		} catch {
			error = $_('admin.scrapers.saveError');
		} finally {
			saving = false;
		}
	}

	async function addTime(row: Row): Promise<void> {
		if (!canAdd(row)) return;
		await persist(row, [...row.times, toHHMMSS(row.addValue)], row.enabled);
		row.addValue = '';
	}

	async function removeTime(row: Row, t: string): Promise<void> {
		if (saving) return;
		await persist(
			row,
			row.times.filter((x) => x !== t),
			row.enabled
		);
	}

	async function toggleActive(row: Row): Promise<void> {
		await persist(row, row.times, !row.enabled);
	}

	// Removing a run (the table × or a timeline marker) asks for confirmation first.
	let pendingRemoval = $state<{ id: string; time: string } | null>(null);

	const pendingInfo = $derived.by(() => {
		const p = pendingRemoval;
		if (!p) return null;
		const r = rows.find((x) => x.id === p.id);
		return { time: p.time, name: r?.name ?? p.id };
	});

	function requestRemove(id: string, time: string): void {
		if (!saving) pendingRemoval = { id, time };
	}

	async function confirmRemove(): Promise<void> {
		const p = pendingRemoval;
		pendingRemoval = null;
		if (!p) return;
		const r = rows.find((x) => x.id === p.id);
		if (r) await removeTime(r, p.time);
	}
</script>

<section class="space-y-6">
	<a href="/admin/scrapers" class="text-sm text-sky-600 hover:underline dark:text-sky-400">
		{$_('admin.scrapers.back')}
	</a>

	<PageTitle title={$_('admin.scrapers.scheduleTitle')} />
	<p class="text-sm text-slate-500">{$_('admin.scrapers.scheduleHint')}</p>

	{#if loading}
		<p class="text-sm text-slate-500">{$_('common.loading')}</p>
	{:else if error && rows.length === 0}
		<p class="text-sm text-red-500">{error}</p>
	{:else}
		<!-- Fixed layout: column widths are set, so adding a chip never resizes the table. -->
		<table class="w-[58rem] max-w-full table-fixed text-left text-sm">
			<colgroup>
				<col style="width: 13rem" />
				<col style="width: 24rem" />
				<col style="width: 16rem" />
				<col style="width: 5rem" />
			</colgroup>
			<thead class="border-b border-slate-200 text-xs text-slate-500 dark:border-slate-800">
				<tr>
					<th class="py-2 pr-4">{$_('admin.scrapers.colName')}</th>
					<th class="py-2 pr-4">{$_('admin.scrapers.colSchedule')}</th>
					<th class="py-2 pr-4">{$_('admin.scrapers.colAdd')}</th>
					<th class="py-2 text-center">{$_('admin.scrapers.colActive')}</th>
				</tr>
			</thead>
			<tbody>
				{#each rows as row (row.id)}
					<tr class="border-b border-slate-100 align-top dark:border-slate-800/60">
						<td class="py-3 pr-4 font-medium whitespace-nowrap">
							{#if row.icon}
								<img src={row.icon} alt="" class="mr-2 inline h-4 w-4 align-text-bottom" />
							{/if}{row.name}
						</td>

						<td class="py-3 pr-4">
							{#if !row.schedulable}
								<span class="text-slate-400">{$_('admin.scrapers.notSchedulable')}</span>
							{:else if row.times.length === 0}
								<span class="text-slate-400">{$_('admin.scrapers.noTimes')}</span>
							{:else}
								<div class="flex flex-wrap gap-1.5">
									{#each row.times as t (t)}
										<span
											class="inline-flex items-center gap-1 rounded bg-slate-100 px-2 py-0.5 font-mono text-xs dark:bg-slate-800"
											class:opacity-50={!row.enabled}
										>
											{t}
											<button
												type="button"
												class="text-slate-400 hover:text-red-600 disabled:opacity-40 dark:hover:text-red-400"
												aria-label={`remove ${t}`}
												onclick={() => requestRemove(row.id, t)}
												disabled={saving}>×</button
											>
										</span>
									{/each}
								</div>
							{/if}
						</td>

						<td class="py-3 pr-4">
							{#if row.schedulable}
								<div class="flex flex-col gap-1">
									<div class="flex items-center gap-2">
										<input
											type="time"
											step="1"
											bind:value={row.addValue}
											class="rounded border border-slate-300 bg-white px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-900"
										/>
										<button
											type="button"
											class="rounded bg-slate-800 px-3 py-1 text-sm text-white hover:bg-slate-700 disabled:opacity-40 dark:bg-slate-200 dark:text-slate-900 dark:hover:bg-white"
											onclick={() => addTime(row)}
											disabled={!canAdd(row)}
										>
											{$_('admin.scrapers.addAction')}
										</button>
									</div>
									{#if tooClose(row)}
										<span class="text-xs text-red-500">{$_('admin.scrapers.tooClose')}</span>
									{/if}
								</div>
							{:else}
								<span class="text-slate-400">—</span>
							{/if}
						</td>

						<td class="py-3 text-center align-middle">
							{#if row.schedulable}
								<input
									type="checkbox"
									checked={row.enabled}
									onchange={() => toggleActive(row)}
									disabled={saving}
									aria-label={$_('admin.scrapers.colActive')}
								/>
							{:else}
								<span class="text-slate-400">—</span>
							{/if}
						</td>
					</tr>
				{/each}
			</tbody>
		</table>

		{#if error}<p class="text-sm text-red-500">{error}</p>{/if}

		<ScheduleTimeline scrapers={rows} onRemove={requestRemove} />
	{/if}

	{#if pendingInfo}
		<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
			<div
				class="w-full max-w-sm rounded-lg border border-slate-200 bg-white p-5 shadow-xl dark:border-slate-700 dark:bg-slate-900"
				role="dialog"
				aria-modal="true"
			>
				<p class="text-sm">
					{$_('admin.scrapers.removeConfirm', {
						values: { time: pendingInfo.time, name: pendingInfo.name }
					})}
				</p>
				<div class="mt-4 flex justify-end gap-3">
					<button
						type="button"
						class="rounded border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800"
						onclick={() => (pendingRemoval = null)}
					>
						{$_('common.cancel')}
					</button>
					<button
						type="button"
						class="rounded bg-red-700 px-3 py-1.5 text-sm text-white hover:bg-red-600 disabled:opacity-40"
						onclick={confirmRemove}
						disabled={saving}
					>
						{$_('admin.scrapers.removeAction')}
					</button>
				</div>
			</div>
		</div>
	{/if}
</section>
