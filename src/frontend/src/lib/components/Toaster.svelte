<script lang="ts">
	// Single toast portal (phase 7 design-system): top-center, above everything, non-blocking.
	// Mounted once at the app-shell root; renders one <Banner> per queued toast. Reused by any
	// feature (notifiers today) via pushToast().
	import Banner from '$lib/components/Banner.svelte';
	import { toasts, dismissToast, type ToastVariant } from '$lib/stores/toasts';

	const ICON: Record<ToastVariant, string> = { success: '✅', error: '⚠️', info: 'ℹ️' };
</script>

{#if $toasts.length > 0}
	<div
		class="pointer-events-none fixed top-4 left-1/2 z-[100] flex w-full max-w-md -translate-x-1/2 flex-col gap-2 px-4"
	>
		{#each $toasts as t (t.id)}
			<div class="pointer-events-auto">
				<Banner variant={t.variant} icon={ICON[t.variant]} onClose={() => dismissToast(t.id)}>
					<p class="whitespace-pre-line">{t.message}</p>
				</Banner>
			</div>
		{/each}
	</div>
{/if}
