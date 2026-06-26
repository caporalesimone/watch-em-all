<script lang="ts">
	// Admin scrapers index (4.F2): lists the schedulable scrapers with their version and a
	// schedule summary, linking to each scraper's config subpage. The slot editor (4.F1) and
	// the plugin-declared fields (phase 7+) land on the subpage later.
	import { onMount } from 'svelte';
	import { _ } from 'svelte-i18n';

	import { getPlugins, listScrapers, type ScraperListItem } from '$lib/api/client';
	import PageTitle from '$lib/components/PageTitle.svelte';

	let scrapers = $state<ScraperListItem[]>([]);
	let versions = $state<Record<string, string>>({});
	let loading = $state(true);
	let error = $state<string | null>(null);

	onMount(async () => {
		try {
			const [list, plugins] = await Promise.all([listScrapers(), getPlugins()]);
			scrapers = list;
			versions = Object.fromEntries(plugins.map((p) => [p.name, p.version]));
		} catch {
			error = $_('admin.scrapers.loadError');
		} finally {
			loading = false;
		}
	});

	function scheduleSummary(s: ScraperListItem): string {
		if (!s.enabled) return $_('admin.scrapers.suspended');
		if (s.times.length === 0) return $_('admin.scrapers.noSchedule');
		return s.times.join(', ');
	}
</script>

<section class="space-y-6">
	<PageTitle title={$_('admin.scrapers.title')} />
	<p class="text-sm text-slate-500">{$_('admin.scrapers.hint')}</p>

	{#if loading}
		<p class="text-sm text-slate-500">{$_('common.loading')}</p>
	{:else if error}
		<p class="text-sm text-red-500">{error}</p>
	{:else if scrapers.length === 0}
		<p class="text-sm text-slate-500">{$_('admin.scrapers.empty')}</p>
	{:else}
		<table class="w-full max-w-2xl text-left text-sm">
			<thead class="border-b border-slate-200 text-xs text-slate-500 dark:border-slate-800">
				<tr>
					<th class="py-2 pr-4">{$_('admin.scrapers.colName')}</th>
					<th class="py-2 pr-4">{$_('admin.scrapers.colVersion')}</th>
					<th class="py-2 pr-4">{$_('admin.scrapers.colSchedule')}</th>
					<th class="py-2 pr-4"></th>
				</tr>
			</thead>
			<tbody>
				{#each scrapers as s (s.scraper_id)}
					<tr class="border-b border-slate-100 dark:border-slate-800/60">
						<td class="py-2 pr-4 font-medium">{s.display_name}</td>
						<td class="py-2 pr-4 font-mono text-slate-500">{versions[s.scraper_id] ?? '—'}</td>
						<td class="py-2 pr-4 font-mono text-slate-500">{scheduleSummary(s)}</td>
						<td class="py-2 pr-4">
							<a
								class="text-sky-600 hover:underline dark:text-sky-400"
								href={`/admin/scrapers/${s.scraper_id}`}
							>
								{$_('admin.scrapers.configure')}
							</a>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	{/if}
</section>
