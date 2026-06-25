<script lang="ts">
	// Generic alert block (FE-8/FE-18): a bordered, translucent bar with a big icon on
	// the left, the title + slotted body to its right, and an optional top-right action.
	// It does NOT position itself — the caller places/stacks it (e.g. a fixed container),
	// so it is reusable anywhere, not only as a bottom bar.
	import type { Snippet } from 'svelte';

	type Variant = 'error' | 'warning' | 'info' | 'success';

	let {
		variant = 'info',
		icon,
		title,
		action,
		children
	}: {
		variant?: Variant;
		icon?: string;
		title?: string;
		action?: Snippet; // optional top-right action (e.g. a button)
		children?: Snippet;
	} = $props();

	// top border + translucent background per variant; text colour picked for contrast.
	const VARIANT: Record<Variant, string> = {
		error: 'border-red-950 bg-red-800/75 text-white',
		warning: 'border-amber-800 bg-amber-500/80 text-amber-950',
		info: 'border-sky-950 bg-sky-700/80 text-white',
		success: 'border-emerald-950 bg-emerald-700/80 text-white'
	};
</script>

<div
	role="alert"
	class="flex w-full items-start gap-3 border-t-2 px-4 py-2 text-sm shadow-lg {VARIANT[variant]}"
>
	{#if icon}
		<span class="shrink-0 self-start text-4xl leading-none" aria-hidden="true">{icon}</span>
	{/if}
	<div class="min-w-0 flex-1">
		{#if title}<p class="font-semibold">{title}</p>{/if}
		{#if children}{@render children()}{/if}
	</div>
	{#if action}<div class="shrink-0 self-start">{@render action()}</div>{/if}
</div>
