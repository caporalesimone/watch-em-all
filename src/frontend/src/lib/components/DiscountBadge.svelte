<script lang="ts">
	// The green `-NN%` discount badge, shown under the current price when discounted.
	// Shared widget (phase 5 mini-SDK). `discountPct` is the API's Decimal string.
	let { discountPct }: { discountPct: string } = $props();
	const pct = $derived(Math.round(Number(discountPct)));
</script>

{#if pct > 0}
	<span
		class="mt-0.5 inline-block rounded bg-green-100 px-1.5 py-0.5 text-xs text-green-700 dark:bg-green-900/40 dark:text-green-300"
		>-{pct}%</span
	>
{/if}
