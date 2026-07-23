<script lang="ts">
	// Price-history page (8.F3): one chart, two sources. A Product|Cart toggle + a picker choose
	// what to plot; entry points (Catalog row, cart detail) deep-link here via ?product= / ?cart=.
	// The chart component is source-agnostic — this page just maps each API series to {t,value,available}.
	import { onMount } from 'svelte';
	import { _ } from 'svelte-i18n';

	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import {
		getCartHistory,
		getProductHistory,
		listCarts,
		listCatalog,
		type CartCard,
		type CatalogItem,
		type HistoryRange
	} from '$lib/api/client';
	import PageTitle from '$lib/components/PageTitle.svelte';
	import PriceChart from '$lib/components/PriceChart.svelte';

	type Source = 'product' | 'cart';
	type ChartPoint = { t: string; value: number; available: boolean };

	let products = $state<CatalogItem[]>([]);
	let carts = $state<CartCard[]>([]);
	let source = $state<Source>('product');
	let productId = $state<number | null>(null);
	let cartId = $state<number | null>(null);
	let range = $state<HistoryRange>('month');

	let points = $state<ChartPoint[]>([]);
	let currency = $state('EUR');
	let loading = $state(true);
	let error = $state<string | null>(null);

	async function loadHistory(): Promise<void> {
		loading = true;
		error = null;
		try {
			if (source === 'product' && productId != null) {
				const h = await getProductHistory(productId, range);
				points = h.points.map((p) => ({ t: p.t, value: Number(p.price), available: p.available }));
				currency = products.find((p) => p.id === productId)?.currency ?? 'EUR';
			} else if (source === 'cart' && cartId != null) {
				const h = await getCartHistory(cartId, range);
				points = h.points.map((p) => ({ t: p.t, value: Number(p.total), available: true }));
				currency = carts.find((c) => c.id === cartId)?.currency ?? 'EUR';
			} else {
				points = [];
			}
		} catch {
			error = $_('priceHistory.error');
			points = [];
		} finally {
			loading = false;
		}
	}

	function syncUrl(): void {
		const target =
			source === 'product' && productId != null
				? `/price-history?product=${productId}`
				: source === 'cart' && cartId != null
					? `/price-history?cart=${cartId}`
					: '/price-history';
		void goto(target, { replaceState: true, keepFocus: true, noScroll: true });
	}

	function pickProduct(id: number): void {
		source = 'product';
		productId = id;
		syncUrl();
		void loadHistory();
	}

	function pickCart(id: number): void {
		source = 'cart';
		cartId = id;
		syncUrl();
		void loadHistory();
	}

	function switchSource(next: Source): void {
		source = next;
		if (next === 'product') productId = productId ?? products[0]?.id ?? null;
		else cartId = cartId ?? carts[0]?.id ?? null;
		syncUrl();
		void loadHistory();
	}

	function onRangeChange(r: HistoryRange): void {
		range = r;
		void loadHistory();
	}

	onMount(async () => {
		try {
			const [cat, cs] = await Promise.all([listCatalog({ page_size: 100 }), listCarts()]);
			products = cat.items;
			carts = cs;
		} catch {
			error = $_('priceHistory.error');
		}

		const params = $page.url.searchParams;
		const pid = params.get('product');
		const cid = params.get('cart');
		if (cid) {
			source = 'cart';
			cartId = Number(cid);
		} else if (pid) {
			source = 'product';
			productId = Number(pid);
		} else if (products.length) {
			productId = products[0].id;
		} else if (carts.length) {
			source = 'cart';
			cartId = carts[0].id;
		}
		await loadHistory();
	});

	const seg =
		'rounded px-3 py-1 text-sm font-medium border border-slate-300 dark:border-slate-700 transition';
	const segOn = 'bg-indigo-600 text-white border-indigo-600';
	const select =
		'w-72 rounded border border-slate-300 bg-white px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-900';
</script>

<section class="max-w-4xl space-y-6">
	<PageTitle title={$_('priceHistory.title')} />

	<div class="flex flex-wrap items-center gap-3">
		<div class="flex gap-2">
			<button
				type="button"
				class="{seg} {source === 'product' ? segOn : ''}"
				onclick={() => switchSource('product')}
			>
				{$_('priceHistory.product')}
			</button>
			<button
				type="button"
				class="{seg} {source === 'cart' ? segOn : ''}"
				onclick={() => switchSource('cart')}
			>
				{$_('priceHistory.cart')}
			</button>
		</div>

		{#if source === 'product'}
			<select
				class={select}
				value={productId}
				onchange={(e) => pickProduct(Number(e.currentTarget.value))}
			>
				{#if products.length === 0}
					<option value={null}>{$_('priceHistory.noProducts')}</option>
				{/if}
				{#each products as p (p.id)}
					<option value={p.id}>{p.name}</option>
				{/each}
			</select>
		{:else}
			<select
				class={select}
				value={cartId}
				onchange={(e) => pickCart(Number(e.currentTarget.value))}
			>
				{#if carts.length === 0}
					<option value={null}>{$_('priceHistory.noCarts')}</option>
				{/if}
				{#each carts as c (c.id)}
					<option value={c.id}>{c.name}</option>
				{/each}
			</select>
		{/if}
	</div>

	{#if error}
		<p class="text-sm text-red-500">{error}</p>
	{/if}

	<PriceChart {points} {range} {onRangeChange} {currency} {loading} />
</section>
