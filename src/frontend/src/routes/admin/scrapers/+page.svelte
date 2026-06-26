<script lang="ts">
	// Admin Scrapers menu: every scraper plugin (icon + name, version, cache size). Schedulable
	// scrapers link to their config subpage; a stub that can't be scheduled is marked as such.
	// The schedule itself is edited from the Scrapers → Schedule sidebar entry.
	import { onMount } from 'svelte';
	import { _ } from 'svelte-i18n';

	import { getPlugins, listScrapers, type PluginInfo, type ScraperListItem } from '$lib/api/client';
	import PageTitle from '$lib/components/PageTitle.svelte';

	type Row = { plugin: PluginInfo; sched: ScraperListItem | undefined };

	let rows = $state<Row[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	onMount(async () => {
		try {
			const [plugins, scrapers] = await Promise.all([getPlugins(), listScrapers()]);
			const byId = new Map(scrapers.map((s) => [s.scraper_id, s]));
			rows = plugins
				.filter((p) => p.type === 'scraper')
				.map((plugin) => ({ plugin, sched: byId.get(plugin.name) }));
		} catch {
			error = $_('admin.scrapers.loadError');
		} finally {
			loading = false;
		}
	});
</script>

<section class="space-y-6">
	<PageTitle title={$_('admin.scrapers.title')} />
	<p class="text-sm text-slate-500">{$_('admin.scrapers.hint')}</p>

	{#if loading}
		<p class="text-sm text-slate-500">{$_('common.loading')}</p>
	{:else if error}
		<p class="text-sm text-red-500">{error}</p>
	{:else if rows.length === 0}
		<p class="text-sm text-slate-500">{$_('admin.scrapers.empty')}</p>
	{:else}
		<table class="w-full max-w-3xl table-fixed text-left text-sm">
			<colgroup>
				<col style="width: 15rem" />
				<col style="width: 6rem" />
				<col style="width: 6rem" />
				<col />
			</colgroup>
			<thead class="border-b border-slate-200 text-xs text-slate-500 dark:border-slate-800">
				<tr>
					<th class="py-2 pr-4">{$_('admin.scrapers.colName')}</th>
					<th class="py-2 pr-4">{$_('admin.scrapers.colVersion')}</th>
					<th class="py-2 pr-4">{$_('admin.scrapers.colCache')}</th>
					<th class="py-2 pr-4"></th>
				</tr>
			</thead>
			<tbody>
				{#each rows as { plugin, sched } (plugin.name)}
					<tr class="border-b border-slate-100 dark:border-slate-800/60">
						<td class="py-2 pr-4 font-medium whitespace-nowrap">
							{#if plugin.icon}
								<img src={plugin.icon} alt="" class="mr-2 inline h-4 w-4 align-text-bottom" />
							{/if}{plugin.display_name}
						</td>
						<td class="py-2 pr-4 font-mono text-slate-500">{plugin.version}</td>
						<td class="py-2 pr-4 font-mono text-slate-500">{sched ? sched.cache_entries : '—'}</td>
						<td class="py-2 pr-4">
							{#if sched}
								<a
									class="text-sky-600 hover:underline dark:text-sky-400"
									href={`/admin/scrapers/${plugin.name}`}
								>
									{$_('admin.scrapers.configure')}
								</a>
							{:else}
								<span class="text-slate-400">{$_('admin.scrapers.notSchedulable')}</span>
							{/if}
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	{/if}
</section>
