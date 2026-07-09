<script lang="ts">
	// Category breadcrumb (root → leaf), packed tight: the markup carries NO whitespace
	// between the inline elements, so the only gaps are the `/` separator's own padding
	// (a stray space here was the original Catalog spacing bug). Shared widget — change
	// it once, every page/plugin gets the same look (phase 5 mini-SDK; FE-18 / 12.F4).
	let { category }: { category: { text: string; link: string | null }[] } = $props();
</script>

{#if category.length > 0}
	<div class="mt-1 text-xs text-slate-400">
		{#each category as cat, i (cat.text + i)}{#if i > 0}<span class="px-1">/</span
				>{/if}{#if cat.link}<a
					href={cat.link}
					target="_blank"
					rel="noopener noreferrer"
					class="hover:underline">{cat.text}</a
				>{:else}{cat.text}{/if}{/each}
	</div>
{/if}
