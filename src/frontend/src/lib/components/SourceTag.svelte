<script lang="ts">
	// Provenance: a scraper's icon + display name, resolved from the mounted plugins by
	// plugin_id (so every page shows the same source chip). `link` makes it a link to the
	// scraper's page. Shared widget (phase 5 mini-SDK).
	import { mountedPlugins } from '$lib/stores/plugins';

	let { pluginId, link = false }: { pluginId: string; link?: boolean } = $props();

	const plugin = $derived($mountedPlugins.find((m) => m.name === pluginId));
	const name = $derived(plugin?.display_name ?? pluginId);
	const icon = $derived(plugin?.icon ?? null);
	const route = $derived(plugin?.route_base ?? null);
</script>

{#if link && route}
	<a
		href={route}
		class="flex items-center gap-2 text-slate-500 hover:text-slate-800 hover:underline dark:hover:text-slate-200"
		title={name}
	>
		{#if icon}<img src={icon} alt="" class="h-4 w-4" />{/if}<span>{name}</span>
	</a>
{:else}
	<span class="flex items-center gap-2 text-slate-500" title={name}>
		{#if icon}<img src={icon} alt="" class="h-4 w-4" />{/if}<span>{name}</span>
	</span>
{/if}
