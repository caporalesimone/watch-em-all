<script lang="ts">
	// Generic alert card (FE-8/FE-18): a bordered, rounded, translucent box with a big
	// icon on the left, the title + slotted body to its right, an optional top-right
	// action, and an optional close (✕). It does NOT position itself — the caller
	// places/stacks it (e.g. a fixed container), so it is reusable anywhere.
	import type { Snippet } from 'svelte';

	type Variant = 'error' | 'warning' | 'info' | 'success';

	let {
		variant = 'info',
		icon,
		title,
		action,
		onClose,
		children
	}: {
		variant?: Variant;
		icon?: string;
		title?: string;
		action?: Snippet; // optional top-right action (e.g. a button)
		onClose?: () => void; // when set, renders a ✕ that calls this
		children?: Snippet;
	} = $props();

	// border + translucent background per variant; text colour picked for contrast.
	const VARIANT: Record<Variant, string> = {
		error: 'border-red-300/50 bg-red-800/75 text-white',
		warning: 'border-amber-700/50 bg-amber-400/80 text-amber-950',
		info: 'border-sky-300/50 bg-sky-700/80 text-white',
		success: 'border-emerald-300/50 bg-emerald-700/80 text-white'
	};
</script>

<div
	role="alert"
	class="flex w-full items-start gap-3 rounded-lg border px-4 py-3 text-sm shadow-lg {VARIANT[
		variant
	]}"
>
	{#if icon}
		<span class="shrink-0 self-start text-4xl leading-none" aria-hidden="true">{icon}</span>
	{/if}
	<div class="min-w-0 flex-1">
		{#if title}<p class="font-semibold">{title}</p>{/if}
		{#if children}{@render children()}{/if}
	</div>
	{#if action}<div class="shrink-0 self-start">{@render action()}</div>{/if}
	{#if onClose}
		<button
			type="button"
			onclick={onClose}
			aria-label="Close"
			class="shrink-0 self-start rounded p-1 hover:bg-black/10"
		>
			<svg
				class="h-4 w-4"
				viewBox="0 0 24 24"
				fill="none"
				stroke="currentColor"
				stroke-width="2"
				stroke-linecap="round"
				aria-hidden="true"
			>
				<path d="M6 6l12 12M18 6 6 18" />
			</svg>
		</button>
	{/if}
</div>
