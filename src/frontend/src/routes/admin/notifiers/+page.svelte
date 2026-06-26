<script lang="ts">
	// Admin Notifiers menu: the notifier plugins in the plugins-style table (icon + name,
	// version). Informational for now — notifier admin config arrives in phase 7+.
	import { onMount } from 'svelte';
	import { _ } from 'svelte-i18n';

	import { getPlugins, type PluginInfo } from '$lib/api/client';
	import PageTitle from '$lib/components/PageTitle.svelte';

	let notifiers = $state<PluginInfo[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	onMount(async () => {
		try {
			notifiers = (await getPlugins()).filter((p) => p.type === 'notifier');
		} catch {
			error = $_('admin.notifiers.loadError');
		} finally {
			loading = false;
		}
	});
</script>

<section class="space-y-6">
	<PageTitle title={$_('admin.notifiers.title')} />

	{#if loading}
		<p class="text-sm text-slate-500">{$_('common.loading')}</p>
	{:else if error}
		<p class="text-sm text-red-500">{error}</p>
	{:else if notifiers.length === 0}
		<p class="text-sm text-slate-500">{$_('admin.notifiers.empty')}</p>
	{:else}
		<table class="w-full max-w-2xl text-left text-sm">
			<thead class="border-b border-slate-200 text-xs text-slate-500 dark:border-slate-800">
				<tr>
					<th class="py-2 pr-4">{$_('admin.notifiers.colName')}</th>
					<th class="py-2 pr-4">{$_('admin.notifiers.colVersion')}</th>
				</tr>
			</thead>
			<tbody>
				{#each notifiers as n (n.name)}
					<tr class="border-b border-slate-100 dark:border-slate-800/60">
						<td class="py-2 pr-4 font-medium">
							{#if n.icon}
								<img src={n.icon} alt="" class="mr-2 inline h-4 w-4 align-text-bottom" />
							{/if}{n.display_name}
						</td>
						<td class="py-2 pr-4 font-mono text-slate-500">{n.version}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	{/if}
</section>
