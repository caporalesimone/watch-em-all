<script lang="ts">
	// Product thumbnail with a hover-zoom preview revealed after a short intent delay
	// (so it doesn't flash while scrolling). Self-contained: each thumb owns its state.
	// Shared by the Catalog, the cart detail and the scraper pages (phase 5 mini-SDK).
	let { src = null, alt = '' }: { src?: string | null; alt?: string } = $props();

	const HOVER_DELAY_MS = 500;
	let hovered = $state(false);
	let timer: ReturnType<typeof setTimeout> | null = null;

	function enter(): void {
		if (timer) clearTimeout(timer);
		timer = setTimeout(() => {
			hovered = true;
			timer = null;
		}, HOVER_DELAY_MS);
	}
	function leave(): void {
		if (timer) {
			clearTimeout(timer);
			timer = null;
		}
		hovered = false;
	}
</script>

{#if src}
	<div class="relative inline-block" role="presentation" onmouseenter={enter} onmouseleave={leave}>
		<img
			{src}
			{alt}
			class="h-10 w-10 rounded border border-slate-200 object-cover dark:border-slate-700"
			loading="lazy"
		/>
		<div class="pointer-events-none absolute top-0 left-12 z-20" class:hidden={!hovered}>
			<img
				{src}
				{alt}
				class="max-h-80 max-w-xs rounded-lg border border-slate-200 bg-white p-1 shadow-xl dark:border-slate-700 dark:bg-slate-900"
			/>
		</div>
	</div>
{:else}
	<div
		class="h-10 w-10 rounded border border-slate-200 bg-slate-100 dark:border-slate-700 dark:bg-slate-800"
	></div>
{/if}
