<script lang="ts">
	// Generic fixed bottom alert bar (extracted from the schema-drift banner — FE-8/FE-18:
	// reusable, props-driven). The consumer decides WHEN to show it (wrap in {#if …});
	// this is just the frame: a big icon on the left and the title + slotted body to its
	// right. `sidebarOffset` keeps the bar to the RIGHT of the app sidebar (w-56) so it
	// never covers the menu buttons.
	import type { Snippet } from 'svelte';

	type Variant = 'error' | 'warning' | 'info' | 'success';

	let {
		variant = 'info',
		icon,
		title,
		sidebarOffset = false,
		children
	}: {
		variant?: Variant;
		icon?: string;
		title?: string;
		sidebarOffset?: boolean;
		children?: Snippet;
	} = $props();

	// top border + background per variant; text colour picked for contrast.
	const VARIANT: Record<Variant, string> = {
		error: 'border-red-800 bg-red-600 text-white',
		warning: 'border-amber-600 bg-amber-400 text-amber-950',
		info: 'border-sky-800 bg-sky-600 text-white',
		success: 'border-emerald-800 bg-emerald-600 text-white'
	};
</script>

<div
	role="alert"
	class="fixed right-0 bottom-0 z-50 flex max-h-48 items-start gap-3 overflow-auto border-t-2 px-4 py-2 text-sm shadow-lg {VARIANT[
		variant
	]} {sidebarOffset ? 'left-56' : 'left-0'}"
>
	{#if icon}
		<span class="shrink-0 self-start text-4xl leading-none" aria-hidden="true">{icon}</span>
	{/if}
	<div class="min-w-0 flex-1">
		{#if title}<p class="font-semibold">{title}</p>{/if}
		{#if children}{@render children()}{/if}
	</div>
</div>
