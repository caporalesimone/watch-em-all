<script lang="ts">
	// The "product cell": linkable title + brand + category breadcrumb — the block the
	// Catalog, the cart detail and the scraper pages all repeat. Shared widget so the
	// look is defined once (phase 5 mini-SDK; FE-18 / 12.F4).
	import CategoryBreadcrumb from './CategoryBreadcrumb.svelte';

	let {
		name,
		url = null,
		brand = null,
		category = []
	}: {
		name: string;
		url?: string | null;
		brand?: { text: string; link: string | null } | null;
		category?: { text: string; link: string | null }[];
	} = $props();
</script>

{#if url}
	<a
		href={url}
		target="_blank"
		rel="noopener noreferrer"
		class="font-medium text-sky-700 hover:underline dark:text-sky-400">{name}</a
	>
{:else}
	<span class="font-medium">{name}</span>
{/if}
{#if brand}
	<div class="text-xs text-slate-500">
		{#if brand.link}<a
				href={brand.link}
				target="_blank"
				rel="noopener noreferrer"
				class="hover:underline">{brand.text}</a
			>{:else}{brand.text}{/if}
	</div>
{/if}
<CategoryBreadcrumb {category} />
