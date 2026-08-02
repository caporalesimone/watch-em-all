<script lang="ts">
	// Provenance: a scraper's icon + display name, resolved from the mounted plugins by
	// plugin_id (so every page shows the same source chip). `link` makes it a link to the
	// scraper's page. Shared widget (phase 5 mini-SDK).
	//
	// `iconOnly` (10.F0) drops the name and grows the logo to the size of the product
	// thumbnail next to it, so the two cells line up: on a table repeating the same store on
	// every row the name is noise, and it is the logo that carries the recognition — which a
	// 16px mark cannot do. It is an option rather than a second component because three pages
	// share this one (catalog, cart detail, alert digest) and a copy would let them drift.
	import { mountedPlugins } from '$lib/stores/plugins';

	let {
		pluginId,
		link = false,
		iconOnly = false
	}: { pluginId: string; link?: boolean; iconOnly?: boolean } = $props();

	const plugin = $derived($mountedPlugins.find((m) => m.name === pluginId));
	const name = $derived(plugin?.display_name ?? pluginId);
	const icon = $derived(plugin?.icon ?? null);
	const route = $derived(plugin?.route_base ?? null);

	// Only hide the name when there is a logo to hide it behind: a plugin that ships no icon
	// would otherwise render an empty cell instead of a compact one.
	const compact = $derived(iconOnly && icon !== null);
	// `object-contain`, not the thumbnail's `object-cover`: a cropped logo is a wrong logo.
	const imgClass = $derived(compact ? 'h-10 w-10 object-contain' : 'h-4 w-4');
	// With the name written beside it the alt must stay empty, or a screen reader announces
	// the store twice; alone, the image *is* the information and a silent cell would lose it.
	const imgAlt = $derived(compact ? name : '');
</script>

{#if link && route}
	<a
		href={route}
		class="flex items-center gap-2 text-slate-500 hover:text-slate-800 hover:underline dark:hover:text-slate-200"
		title={name}
	>
		{#if icon}<img src={icon} alt={imgAlt} class={imgClass} />{/if}{#if !compact}<span>{name}</span
			>{/if}
	</a>
{:else}
	<span class="flex items-center gap-2 text-slate-500" title={name}>
		{#if icon}<img src={icon} alt={imgAlt} class={imgClass} />{/if}{#if !compact}<span>{name}</span
			>{/if}
	</span>
{/if}
