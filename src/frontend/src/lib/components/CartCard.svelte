<script lang="ts">
	import { _ } from 'svelte-i18n';

	import { type CartCard } from '$lib/api/client';
	import { mountedPlugins } from '$lib/stores/plugins';

	let { cart }: { cart: CartCard } = $props();

	function money(value: string, currency: string | null): string {
		return !currency || currency === 'EUR' ? `€${value}` : `${value} ${currency}`;
	}

	function sourceName(pluginId: string): string {
		return $mountedPlugins.find((m) => m.name === pluginId)?.display_name ?? pluginId;
	}

	// Read-only threshold bar (the editor lives on the detail page).
	const thrProgress = $derived.by(() => {
		const t = cart.threshold;
		if (!t) return null;
		const full = Number(cart.total_full);
		const target = Number(t.amount);
		const current = Number(t.current);
		const span = full - target;
		const pct =
			span > 0 ? Math.max(0, Math.min(1, (full - current) / span)) * 100 : t.reached ? 100 : 0;
		return { pct, remaining: Math.max(current - target, 0).toFixed(2), reached: t.reached };
	});
</script>

<!-- The whole card is a link to the detail page (no inline interactive controls). -->
<a
	href="/carts/{cart.id}"
	class="block rounded-lg border border-slate-200 p-4 transition hover:border-slate-300 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-900/50"
>
	<div class="flex items-start justify-between gap-2">
		<h3 class="truncate text-base font-semibold">{cart.name}</h3>
		<span class="shrink-0 text-slate-300 dark:text-slate-600">›</span>
	</div>

	<div class="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-400">
		<span class="rounded bg-slate-100 px-1.5 py-0.5 dark:bg-slate-800">
			{cart.mode === 'cross' ? $_('carts.modeCross') : $_('carts.modeSingle')}{#if cart.scraper_id}
				· {sourceName(cart.scraper_id)}{/if}
		</span>
		<span>{$_('carts.products', { values: { count: cart.member_count } })}</span>
		{#if cart.excluded_count > 0}
			<span>· {$_('carts.excludedCount', { values: { count: cart.excluded_count } })}</span>
		{/if}
	</div>

	<div class="mt-2 flex flex-wrap gap-1.5 text-xs">
		{#if cart.all_on_sale}
			<span
				class="rounded bg-emerald-100 px-1.5 py-0.5 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300"
				>{$_('carts.allOnSale')}</span
			>
		{:else if cart.any_on_sale}
			<span
				class="rounded bg-emerald-100 px-1.5 py-0.5 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300"
				>{$_('carts.onSale')}</span
			>
		{/if}
		{#if cart.threshold?.reached}
			<span
				class="rounded bg-amber-100 px-1.5 py-0.5 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300"
				>{$_('carts.thresholdReached')}</span
			>
		{/if}
		{#if cart.has_delisted}
			<span
				class="rounded bg-red-100 px-1.5 py-0.5 text-red-700 dark:bg-red-900/40 dark:text-red-300"
				>⚠ {$_('carts.unhealthy')}</span
			>
		{/if}
	</div>

	<div class="mt-3 flex flex-wrap items-baseline gap-x-4 gap-y-1 text-sm">
		{#if cart.total_full !== cart.total_discounted}
			<span class="text-slate-400 line-through">{money(cart.total_full, cart.currency)}</span>
		{/if}
		<span>{money(cart.total_discounted, cart.currency)}</span>
		<span class="font-semibold">{$_('carts.final')}: {money(cart.final_price, cart.currency)}</span>
	</div>

	{#if thrProgress}
		<div class="mt-2 text-xs">
			<div class="h-2 w-full overflow-hidden rounded bg-slate-100 dark:bg-slate-800">
				<div class="h-full bg-emerald-500" style="width: {thrProgress.pct}%"></div>
			</div>
			<p class="mt-1 text-slate-400">
				{thrProgress.reached
					? $_('carts.thresholdReachedMsg')
					: $_('carts.thresholdRemaining', { values: { remaining: thrProgress.remaining } })}
			</p>
		</div>
	{/if}
</a>
