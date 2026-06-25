<script lang="ts">
	// Admin plugins list (4.B0a): a read-only inventory showing each loaded plugin's
	// type and its own manifest version. The dedicated per-scraper config page is a
	// later MVP (4.F2); this is the minimal "elenco plugin" that surfaces versions now.
	import { onMount } from 'svelte';
	import { _ } from 'svelte-i18n';

	import { getPlugins, type PluginInfo } from '$lib/api/client';
	import PageTitle from '$lib/components/PageTitle.svelte';

	let plugins = $state<PluginInfo[]>([]);
	let loading = $state(true);

	onMount(async () => {
		plugins = await getPlugins();
		loading = false;
	});
</script>

<section class="space-y-6">
	<PageTitle title={$_('admin.plugins.title')} />

	{#if loading}
		<p class="text-sm text-slate-500">{$_('common.loading')}</p>
	{:else if plugins.length === 0}
		<p class="text-sm text-slate-500">{$_('admin.plugins.empty')}</p>
	{:else}
		<table class="w-full max-w-2xl text-left text-sm">
			<thead class="border-b border-slate-200 text-xs text-slate-500 dark:border-slate-800">
				<tr>
					<th class="py-2 pr-4">{$_('admin.plugins.colName')}</th>
					<th class="py-2 pr-4">{$_('admin.plugins.colType')}</th>
					<th class="py-2 pr-4">{$_('admin.plugins.colVersion')}</th>
				</tr>
			</thead>
			<tbody>
				{#each plugins as plugin (plugin.name)}
					<tr class="border-b border-slate-100 dark:border-slate-800/60">
						<td class="py-2 pr-4 font-medium">
							{#if plugin.icon}
								<img src={plugin.icon} alt="" class="mr-2 inline h-4 w-4 align-text-bottom" />
							{/if}{plugin.display_name}
						</td>
						<td class="py-2 pr-4 text-slate-500">{plugin.type}</td>
						<td class="py-2 pr-4 font-mono text-slate-500">{plugin.version}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	{/if}
</section>
