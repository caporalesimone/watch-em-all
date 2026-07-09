<script lang="ts">
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { _ } from 'svelte-i18n';

	import {
		deleteCart,
		getCart,
		patchCart,
		removeCartItems,
		type CartDetail
	} from '$lib/api/client';
	import DiscountBadge from '$lib/components/DiscountBadge.svelte';
	import PageTitle from '$lib/components/PageTitle.svelte';
	import ProductCell from '$lib/components/ProductCell.svelte';
	import ProductTags from '$lib/components/ProductTags.svelte';
	import ProductThumb from '$lib/components/ProductThumb.svelte';
	import SourceTag from '$lib/components/SourceTag.svelte';
	import { money } from '$lib/format';
	import { mountedPlugins } from '$lib/stores/plugins';

	const cartId = $derived(Number($page.params.id));

	let cart = $state<CartDetail | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let busy = $state(false);

	let renaming = $state(false);
	let draftName = $state('');

	async function loadDetail(id: number): Promise<void> {
		loading = true;
		error = null;
		try {
			cart = await getCart(id);
		} catch {
			error = $_('carts.error');
		} finally {
			loading = false;
		}
	}

	$effect(() => {
		void loadDetail(cartId);
	});

	function sourceName(pluginId: string): string {
		return $mountedPlugins.find((m) => m.name === pluginId)?.display_name ?? pluginId;
	}

	function adjDisplay(amount: string, currency: string | null): string {
		const n = Number(amount);
		if (n > 0) return `−${money(amount, currency)}`;
		if (n < 0) return `+${money(amount.replace('-', ''), currency)}`;
		return money(amount, currency);
	}
	function adjClass(amount: string): string {
		const n = Number(amount);
		return n > 0 ? 'text-emerald-600' : n < 0 ? 'text-red-600' : 'text-slate-400';
	}

	async function rename(): Promise<void> {
		if (!cart) return;
		const next = draftName.trim();
		if (!next || next === cart.name) {
			renaming = false;
			return;
		}
		busy = true;
		try {
			cart = await patchCart(cart.id, { name: next });
			renaming = false;
		} finally {
			busy = false;
		}
	}

	async function remove(): Promise<void> {
		if (!cart || !confirm($_('carts.deleteConfirm'))) return;
		busy = true;
		try {
			await deleteCart(cart.id);
			await goto('/carts');
		} finally {
			busy = false;
		}
	}

	async function removeMember(productId: number): Promise<void> {
		if (!cart) return;
		busy = true;
		try {
			cart = await removeCartItems(cart.id, [productId]);
		} finally {
			busy = false;
		}
	}

	async function removeDelisted(): Promise<void> {
		if (!cart) return;
		const ids = cart.members.filter((m) => m.removed).map((m) => m.product_id);
		if (ids.length === 0) return;
		busy = true;
		try {
			cart = await removeCartItems(cart.id, ids);
		} finally {
			busy = false;
		}
	}

	// --- threshold (€, with a % input aid on the current full total) ---
	let editingThreshold = $state(false);
	let thrAmount = $state('');
	let thrPct = $state('');

	function fullTotal(): number {
		return Number(cart?.total_full ?? 0);
	}
	// € ↔ % mirror on the current full total: threshold_amount = full · (1 − pct/100).
	// Each returns '' when the input can't be expressed as the other (empty cart,
	// amount at/above the full price, out-of-range %).
	function amountToPct(amount: string): string {
		const amt = Number(amount);
		const full = fullTotal();
		if (!amount || Number.isNaN(amt) || full <= 0 || amt <= 0 || amt >= full) return '';
		return String(Math.round(((full - amt) / full) * 10000) / 100);
	}
	function pctToAmount(pct: string): string {
		const p = Number(pct);
		const full = fullTotal();
		if (!pct || Number.isNaN(p) || full <= 0 || p <= 0 || p > 100) return '';
		return (full * (1 - p / 100)).toFixed(2);
	}

	function openThreshold(): void {
		thrAmount = cart?.threshold_amount ?? '';
		thrPct = amountToPct(thrAmount);
		editingThreshold = true;
	}

	// Typing in one field fills the other (reads the fresh DOM value; setting the
	// mirror programmatically does not re-fire the opposite field's handler).
	function onAmountInput(e: Event): void {
		thrPct = amountToPct((e.target as HTMLInputElement).value);
	}
	function onPctInput(e: Event): void {
		thrAmount = pctToAmount((e.target as HTMLInputElement).value);
	}

	async function saveThreshold(): Promise<void> {
		if (!cart) return;
		const amt = thrAmount.trim();
		if (!amt || Number(amt) <= 0) return;
		busy = true;
		try {
			cart = await patchCart(cart.id, { threshold_amount: amt });
			editingThreshold = false;
			thrPct = '';
		} finally {
			busy = false;
		}
	}
	async function clearThreshold(): Promise<void> {
		if (!cart) return;
		busy = true;
		try {
			cart = await patchCart(cart.id, { threshold_amount: null });
			editingThreshold = false;
		} finally {
			busy = false;
		}
	}

	const thrProgress = $derived.by(() => {
		const t = cart?.threshold;
		if (!t || !cart) return null;
		const full = Number(cart.total_full);
		const target = Number(t.amount);
		const current = Number(t.current);
		const span = full - target;
		const pct =
			span > 0 ? Math.max(0, Math.min(1, (full - current) / span)) * 100 : t.reached ? 100 : 0;
		return { pct, remaining: Math.max(current - target, 0).toFixed(2), reached: t.reached };
	});

	const th = 'py-2 pr-4 font-normal';
</script>

<section class="space-y-5">
	<a href="/carts" class="text-sm text-slate-500 hover:underline">← {$_('carts.back')}</a>

	{#if loading}
		<p class="text-sm text-slate-500">{$_('common.loading')}</p>
	{:else if error || !cart}
		<p class="text-sm text-red-500">{error}</p>
	{:else}
		<div class="flex items-start justify-between gap-2">
			{#if renaming}
				<div class="flex items-center gap-2">
					<input
						bind:value={draftName}
						class="w-64 rounded border border-slate-300 bg-white px-2 py-1 text-lg dark:border-slate-700 dark:bg-slate-900"
					/>
					<button class="text-sm hover:underline" onclick={rename} disabled={busy}
						>{$_('common.save')}</button
					>
					<button class="text-sm text-slate-500 hover:underline" onclick={() => (renaming = false)}
						>{$_('common.cancel')}</button
					>
				</div>
			{:else}
				<PageTitle title={cart.name} />
			{/if}
			{#if !renaming}
				<div class="flex shrink-0 gap-3 text-sm">
					<button
						class="text-slate-500 hover:underline"
						onclick={() => {
							if (!cart) return;
							renaming = true;
							draftName = cart.name;
						}}>{$_('carts.rename')}</button
					>
					<button class="text-red-600 hover:underline" onclick={remove} disabled={busy}
						>{$_('carts.delete')}</button
					>
				</div>
			{/if}
		</div>

		<div class="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-400">
			<span class="rounded bg-slate-100 px-1.5 py-0.5 dark:bg-slate-800">
				{cart.mode === 'cross'
					? $_('carts.modeCross')
					: $_('carts.modeSingle')}{#if cart.scraper_id}
					· {sourceName(cart.scraper_id)}{/if}
			</span>
			<span>{$_('carts.products', { values: { count: cart.member_count } })}</span>
			{#if cart.excluded_count > 0}
				<span>· {$_('carts.excludedCount', { values: { count: cart.excluded_count } })}</span>
			{/if}
		</div>

		<!-- Badges -->
		<div class="flex flex-wrap gap-1.5 text-xs">
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

		<!-- Totals + adjustments -->
		<div class="rounded-lg border border-slate-200 p-4 dark:border-slate-800">
			<div class="flex flex-wrap items-baseline gap-x-4 gap-y-1 text-sm">
				{#if cart.total_full !== cart.total_discounted}
					<span class="text-slate-400 line-through">{money(cart.total_full, cart.currency)}</span>
				{/if}
				<span>{money(cart.total_discounted, cart.currency)}</span>
				<span class="font-semibold"
					>{$_('carts.final')}: {money(cart.final_price, cart.currency)}</span
				>
			</div>
			{#if cart.adjustments.length > 0}
				<dl class="mt-2 space-y-0.5 text-xs">
					{#each cart.adjustments as adj (adj.id)}
						<div class="flex justify-between gap-2">
							<dt class="text-slate-500">{$_(adj.id, { values: adj.params })}</dt>
							<dd class={adjClass(adj.amount)}>{adjDisplay(adj.amount, cart.currency)}</dd>
						</div>
					{/each}
				</dl>
			{/if}

			<!-- Threshold -->
			<div class="mt-3 border-t border-slate-100 pt-3 text-xs dark:border-slate-800">
				{#if editingThreshold}
					<div class="space-y-2">
						<div class="flex flex-wrap items-end gap-3">
							<label class="text-slate-500"
								>{$_('carts.thresholdTarget')}
								<input
									bind:value={thrAmount}
									oninput={onAmountInput}
									inputmode="decimal"
									class="ml-1 w-24 rounded border border-slate-300 bg-white px-2 py-1 dark:border-slate-700 dark:bg-slate-900"
								/></label
							>
							<label class="text-slate-500"
								>{$_('carts.thresholdPct')}
								<input
									bind:value={thrPct}
									oninput={onPctInput}
									inputmode="decimal"
									class="ml-1 w-16 rounded border border-slate-300 bg-white px-2 py-1 dark:border-slate-700 dark:bg-slate-900"
								/></label
							>
						</div>
						<div class="flex gap-3">
							<button
								class="hover:underline"
								onclick={saveThreshold}
								disabled={busy || !thrAmount.trim()}>{$_('common.save')}</button
							>
							{#if cart.threshold_amount}
								<button
									class="text-red-600 hover:underline"
									onclick={clearThreshold}
									disabled={busy}>{$_('carts.thresholdClear')}</button
								>
							{/if}
							<button
								class="text-slate-500 hover:underline"
								onclick={() => (editingThreshold = false)}>{$_('common.cancel')}</button
							>
						</div>
					</div>
				{:else}
					<div class="flex items-center justify-between gap-2">
						{#if cart.threshold_amount}
							<span class="text-slate-500"
								>{$_('carts.thresholdTitle')}:
								<strong>{money(cart.threshold_amount, cart.currency)}</strong></span
							>
						{:else}
							<span class="text-slate-400">{$_('carts.thresholdNone')}</span>
						{/if}
						<button class="shrink-0 text-slate-500 hover:underline" onclick={openThreshold}
							>{$_('carts.thresholdSet')}</button
						>
					</div>
					{#if thrProgress}
						<div class="mt-2">
							<div class="h-2 w-full overflow-hidden rounded bg-slate-100 dark:bg-slate-800">
								<div class="h-full bg-emerald-500" style="width: {thrProgress.pct}%"></div>
							</div>
							<p class="mt-1 text-slate-400">
								{thrProgress.reached
									? $_('carts.thresholdReachedMsg')
									: $_('carts.thresholdRemaining', {
											values: { remaining: thrProgress.remaining }
										})}
							</p>
						</div>
					{/if}
				{/if}
			</div>
		</div>

		{#if cart.has_delisted}
			<button class="text-xs text-red-600 hover:underline" onclick={removeDelisted} disabled={busy}
				>{$_('carts.removeDelisted')}</button
			>
		{/if}

		<!-- Product table -->
		{#if cart.members.length === 0}
			<p class="max-w-prose text-sm text-slate-500">{$_('carts.noProducts')}</p>
		{:else}
			<table class="w-full text-left text-sm">
				<thead class="border-b border-slate-200 text-xs text-slate-500 dark:border-slate-800">
					<tr>
						{#if cart.mode === 'cross'}
							<th class={th}>{$_('catalog.colSource')}</th>
						{/if}
						<th class={th}>{$_('catalog.colImage')}</th>
						<th class={th}>{$_('catalog.colName')}</th>
						<th class={th}>{$_('catalog.colTags')}</th>
						<th class={th}>{$_('catalog.colPriceOriginal')}</th>
						<th class={th}>{$_('catalog.colPriceCurrent')}</th>
						<th class={th}>{$_('catalog.colAvailability')}</th>
						<th class={th}></th>
					</tr>
				</thead>
				<tbody>
					{#each cart.members as m (m.product_id)}
						<tr
							class="border-b border-slate-100 dark:border-slate-800/60"
							class:opacity-50={!m.active}
						>
							{#if cart.mode === 'cross'}
								<td class="py-2 pr-4"><SourceTag pluginId={m.plugin_id} /></td>
							{/if}
							<td class="py-2 pr-4"><ProductThumb src={m.image_url} /></td>
							<td class="py-2 pr-4">
								<ProductCell name={m.name} url={m.url} brand={m.brand} category={m.category} />
							</td>
							<td class="py-2 pr-4"><ProductTags tags={m.tags} /></td>
							<td class="py-2 pr-4 text-slate-400" class:line-through={Number(m.discount_pct) > 0}
								>{money(m.price_original, m.currency)}</td
							>
							<td class="py-2 pr-4 font-medium">
								<div>{money(m.price_current, m.currency)}</div>
								<DiscountBadge discountPct={m.discount_pct} />
							</td>
							<td class="py-2 pr-4">
								{#if m.removed}
									<span class="text-red-600">{$_('carts.statusDelisted')}</span>
								{:else if m.is_available}
									{$_('catalog.available')}
								{:else}
									<span class="text-slate-500">{$_('carts.statusOutOfStock')}</span>
								{/if}
							</td>
							<td class="py-2 pr-4 text-right">
								<button
									class="text-xs text-red-600 hover:underline"
									onclick={() => removeMember(m.product_id)}
									disabled={busy}>{$_('carts.removeItem')}</button
								>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		{/if}
	{/if}
</section>
