<script lang="ts">
	import { _ } from 'svelte-i18n';

	import {
		deleteCart,
		getCart,
		patchCart,
		removeCartItems,
		type CartCard,
		type CartDetail
	} from '$lib/api/client';
	import { mountedPlugins } from '$lib/stores/plugins';

	let {
		cart,
		onChanged,
		onDeleted
	}: {
		cart: CartCard;
		onChanged: (c: CartCard) => void;
		onDeleted: (id: number) => void;
	} = $props();

	let renaming = $state(false);
	let draftName = $state(''); // seeded from cart.name when entering rename mode
	let busy = $state(false);
	let expanded = $state(false);
	let detail = $state<CartDetail | null>(null);
	let loadingDetail = $state(false);

	function money(value: string, currency: string | null): string {
		return !currency || currency === 'EUR' ? `€${value}` : `${value} ${currency}`;
	}

	function source(pluginId: string): { name: string; icon: string | null } {
		const p = $mountedPlugins.find((m) => m.name === pluginId);
		return { name: p?.display_name ?? pluginId, icon: p?.icon ?? null };
	}

	// An adjustment is signed (+ = saving, − = cost); show its effect on the price.
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

	function applyUpdate(updated: CartDetail): void {
		detail = updated;
		onChanged(updated); // CartDetail extends CartCard → keeps the list summary fresh
	}

	async function rename(): Promise<void> {
		const next = draftName.trim();
		if (!next || next === cart.name) {
			renaming = false;
			return;
		}
		busy = true;
		try {
			onChanged(await patchCart(cart.id, { name: next }));
			renaming = false;
		} finally {
			busy = false;
		}
	}

	async function remove(): Promise<void> {
		if (!confirm($_('carts.deleteConfirm'))) return;
		busy = true;
		try {
			await deleteCart(cart.id);
			onDeleted(cart.id);
		} finally {
			busy = false;
		}
	}

	async function toggle(): Promise<void> {
		expanded = !expanded;
		if (expanded && detail === null) {
			loadingDetail = true;
			try {
				detail = await getCart(cart.id);
			} finally {
				loadingDetail = false;
			}
		}
	}

	async function removeMember(productId: number): Promise<void> {
		busy = true;
		try {
			applyUpdate(await removeCartItems(cart.id, [productId]));
		} finally {
			busy = false;
		}
	}

	async function removeDelisted(): Promise<void> {
		const ids = (detail?.members ?? []).filter((m) => m.removed).map((m) => m.product_id);
		if (ids.length === 0) return;
		busy = true;
		try {
			applyUpdate(await removeCartItems(cart.id, ids));
		} finally {
			busy = false;
		}
	}
</script>

<div class="rounded-lg border border-slate-200 p-4 dark:border-slate-800">
	<div class="flex items-start justify-between gap-2">
		<div class="min-w-0">
			{#if renaming}
				<div class="flex items-center gap-2">
					<input
						bind:value={draftName}
						class="w-48 rounded border border-slate-300 bg-white px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-900"
					/>
					<button class="text-sm hover:underline" onclick={rename} disabled={busy}
						>{$_('common.save')}</button
					>
					<button
						class="text-sm text-slate-500 hover:underline"
						onclick={() => {
							renaming = false;
						}}>{$_('common.cancel')}</button
					>
				</div>
			{:else}
				<h3 class="truncate text-base font-semibold">{cart.name}</h3>
			{/if}
			<div class="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-400">
				<span class="rounded bg-slate-100 px-1.5 py-0.5 dark:bg-slate-800">
					{cart.mode === 'cross'
						? $_('carts.modeCross')
						: $_('carts.modeSingle')}{#if cart.scraper_id}
						· {source(cart.scraper_id).name}{/if}
				</span>
				<span>{$_('carts.products', { values: { count: cart.member_count } })}</span>
				{#if cart.excluded_count > 0}
					<span>· {$_('carts.excludedCount', { values: { count: cart.excluded_count } })}</span>
				{/if}
			</div>
		</div>
		{#if !renaming}
			<div class="flex shrink-0 gap-3 text-xs">
				<button
					class="text-slate-500 hover:underline"
					onclick={() => {
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

	<!-- Status badges -->
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

	<!-- Totals -->
	<div class="mt-3 flex flex-wrap items-baseline gap-x-4 gap-y-1 text-sm">
		{#if cart.total_full !== cart.total_discounted}
			<span class="text-slate-400 line-through">{money(cart.total_full, cart.currency)}</span>
		{/if}
		<span>{money(cart.total_discounted, cart.currency)}</span>
		<span class="font-semibold">{$_('carts.final')}: {money(cart.final_price, cart.currency)}</span>
	</div>

	<!-- Adjustments (scraper_specific) -->
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

	<div class="mt-3 flex items-center gap-3 text-xs">
		<button class="text-slate-500 hover:underline" onclick={toggle}>
			{expanded ? $_('carts.hideProducts') : $_('carts.showProducts')}
		</button>
		{#if cart.has_delisted}
			<button class="text-red-600 hover:underline" onclick={removeDelisted} disabled={busy}>
				{$_('carts.removeDelisted')}
			</button>
		{/if}
	</div>

	{#if expanded}
		{#if loadingDetail}
			<p class="mt-2 text-xs text-slate-500">{$_('common.loading')}</p>
		{:else if detail && detail.members.length > 0}
			<ul class="mt-2 divide-y divide-slate-100 text-sm dark:divide-slate-800">
				{#each detail.members as m (m.product_id)}
					{@const src = source(m.plugin_id)}
					<li class="flex items-center gap-3 py-2" class:opacity-50={!m.active}>
						<span
							class="flex w-28 shrink-0 items-center gap-1 text-xs text-slate-500"
							title={src.name}
						>
							{#if src.icon}<img src={src.icon} alt="" class="h-4 w-4" />{/if}
							<span class="truncate">{src.name}</span>
						</span>
						<a
							href={m.url}
							target="_blank"
							rel="noopener noreferrer"
							class="min-w-0 flex-1 truncate hover:underline">{m.name}</a
						>
						{#if m.removed}
							<span
								class="shrink-0 rounded bg-red-100 px-1.5 py-0.5 text-xs text-red-700 dark:bg-red-900/40 dark:text-red-300"
								>{$_('carts.statusDelisted')}</span
							>
						{:else if !m.is_available}
							<span
								class="shrink-0 rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-500 dark:bg-slate-800"
								>{$_('carts.statusOutOfStock')}</span
							>
						{/if}
						<span class="shrink-0 text-right">
							{#if m.price_current !== m.price_original}
								<span class="mr-1 text-xs text-slate-400 line-through"
									>{money(m.price_original, m.currency)}</span
								>
							{/if}{money(m.price_current, m.currency)}
						</span>
						<button
							class="shrink-0 text-xs text-red-600 hover:underline"
							onclick={() => removeMember(m.product_id)}
							disabled={busy}>{$_('carts.removeItem')}</button
						>
					</li>
				{/each}
			</ul>
		{:else}
			<p class="mt-2 text-xs text-slate-500">{$_('carts.noProducts')}</p>
		{/if}
	{/if}
</div>
