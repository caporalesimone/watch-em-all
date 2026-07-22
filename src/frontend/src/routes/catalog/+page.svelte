<script lang="ts">
	import { onMount } from 'svelte';
	import { _ } from 'svelte-i18n';

	import {
		addCartItems,
		ApiErr,
		listCarts,
		listCatalog,
		type CartCard,
		type CatalogItem,
		type CatalogPage,
		type CatalogSort
	} from '$lib/api/client';
	import DiscountBadge from '$lib/components/DiscountBadge.svelte';
	import PageTitle from '$lib/components/PageTitle.svelte';
	import ProductCell from '$lib/components/ProductCell.svelte';
	import ProductTags from '$lib/components/ProductTags.svelte';
	import ProductThumb from '$lib/components/ProductThumb.svelte';
	import SourceTag from '$lib/components/SourceTag.svelte';
	import { money } from '$lib/format';

	const PAGE_SIZE = 20;

	let data = $state<CatalogPage | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);

	let q = $state('');
	let sort = $state<CatalogSort>('last_seen_at');
	let order = $state<'asc' | 'desc'>('desc');
	let pageNum = $state(1);

	const pages = $derived(data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1);

	// Selection → "add to cart" (5.F4). Delisted rows can't be added (the backend rejects
	// them). We track each selected product's plugin_id (6.F0) so the cart picker can grey
	// out single-store carts that don't match the selection — selection persists across
	// pages, so we can't recover a product's store from the current page alone.
	let selectedIds = $state<number[]>([]);
	let selectedPluginById = $state<Record<number, string>>({});
	let carts = $state<CartCard[]>([]);
	let targetCartId = $state<number | ''>('');
	let adding = $state(false);
	let addMsg = $state<string | null>(null);
	let addErr = $state<string | null>(null);

	// The distinct stores (scraper plugin_ids) covered by the current selection.
	const selectedScrapers = $derived([
		...new Set(selectedIds.map((id) => selectedPluginById[id]).filter(Boolean))
	]);

	// 6.F0: a cross cart always accepts the selection; a scraper_specific cart accepts it
	// only when every selected product comes from that cart's own scraper (matching the
	// server-side rule from 5.B2). Spanning multiple stores disables all single-store carts.
	function cartSelectable(cart: CartCard): boolean {
		if (cart.mode !== 'scraper_specific') return true;
		return selectedScrapers.length <= 1 && selectedScrapers.every((s) => s === cart.scraper_id);
	}

	function toggleSelect(item: CatalogItem): void {
		if (selectedIds.includes(item.id)) {
			selectedIds = selectedIds.filter((x) => x !== item.id);
			const { [item.id]: _drop, ...rest } = selectedPluginById;
			selectedPluginById = rest;
		} else {
			selectedIds = [...selectedIds, item.id];
			selectedPluginById = { ...selectedPluginById, [item.id]: item.plugin_id };
		}
	}

	// If the selection changed so the chosen cart is no longer compatible, drop the choice
	// (never let the user submit into a now-incompatible single-store cart).
	$effect(() => {
		if (targetCartId === '') return;
		const chosen = carts.find((c) => c.id === targetCartId);
		if (chosen && !cartSelectable(chosen)) targetCartId = '';
	});

	// Whether any cart is disabled by the current selection (drives the hint line).
	const someCartDisabled = $derived(
		selectedIds.length > 0 && carts.some((c) => !cartSelectable(c))
	);

	async function loadCarts(): Promise<void> {
		try {
			carts = await listCarts();
		} catch {
			/* the add bar simply offers no carts */
		}
	}

	async function addToCart(): Promise<void> {
		if (targetCartId === '' || selectedIds.length === 0) return;
		adding = true;
		addMsg = null;
		addErr = null;
		try {
			const cart = await addCartItems(Number(targetCartId), selectedIds);
			addMsg = $_('carts.added', { values: { name: cart.name } });
			selectedIds = [];
			selectedPluginById = {};
			carts = carts.map((c) => (c.id === cart.id ? cart : c));
		} catch (e) {
			addErr = e instanceof ApiErr ? e.detail : $_('carts.addError');
		} finally {
			adding = false;
		}
	}

	async function load(silent = false): Promise<void> {
		if (!silent) loading = true;
		error = null;
		try {
			data = await listCatalog({
				page: pageNum,
				page_size: PAGE_SIZE,
				sort,
				order,
				q: q.trim() || undefined
			});
		} catch {
			error = $_('catalog.error');
		} finally {
			if (!silent) loading = false;
		}
	}

	onMount(() => {
		void load();
		void loadCarts();
		// scrape-now writes the catalog asynchronously; if the page is opened while a
		// scrape is still running it would show empty. Retry briefly so the products
		// appear on their own, without a manual search.
		let tries = 0;
		const timer = setInterval(() => {
			if (data && data.total === 0 && tries < 4) {
				tries += 1;
				void load(true);
			} else {
				clearInterval(timer);
			}
		}, 1500);
		return () => clearInterval(timer);
	});

	function search(event: Event): void {
		event.preventDefault();
		pageNum = 1;
		void load();
	}

	function sortBy(col: CatalogSort): void {
		if (sort === col) {
			order = order === 'asc' ? 'desc' : 'asc';
		} else {
			sort = col;
			order = col === 'name' ? 'asc' : 'desc';
		}
		pageNum = 1;
		void load();
	}

	function arrow(col: CatalogSort): string {
		return sort === col ? (order === 'asc' ? ' ↑' : ' ↓') : '';
	}

	function go(delta: number): void {
		const next = pageNum + delta;
		if (next >= 1 && next <= pages) {
			pageNum = next;
			void load();
		}
	}

	function availability(item: CatalogItem): string {
		if (item.removed) return $_('catalog.removed');
		return item.is_available ? $_('catalog.available') : $_('catalog.unavailable');
	}

	const th = 'py-2 pr-4 font-normal';
	const sortable = 'cursor-pointer select-none hover:text-slate-800 dark:hover:text-slate-200';
</script>

<section class="space-y-6">
	<PageTitle title={$_('catalog.title')} />

	<form onsubmit={search} class="flex gap-2">
		<input
			class="w-64 rounded border border-slate-300 bg-white px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-900"
			placeholder={$_('catalog.search')}
			bind:value={q}
		/>
		<button
			type="submit"
			class="rounded border border-slate-300 px-3 py-1 text-sm hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800"
		>
			{$_('catalog.searchAction')}
		</button>
	</form>

	{#if addMsg}
		<p class="text-sm text-emerald-600">{addMsg}</p>
	{/if}
	{#if selectedIds.length > 0}
		<div
			class="flex flex-wrap items-center gap-2 rounded border border-slate-200 bg-slate-50 p-2 text-sm dark:border-slate-700 dark:bg-slate-900"
		>
			<span>{$_('carts.selected', { values: { count: selectedIds.length } })}</span>
			<select
				bind:value={targetCartId}
				class="rounded border border-slate-300 bg-white px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-950"
			>
				<option value="">{$_('carts.chooseCart')}</option>
				{#each carts as c (c.id)}
					<option value={c.id} disabled={!cartSelectable(c)}>{c.name}</option>
				{/each}
			</select>
			<button
				onclick={addToCart}
				disabled={adding || targetCartId === ''}
				class="rounded bg-slate-800 px-3 py-1 text-sm text-white hover:bg-slate-700 disabled:opacity-50 dark:bg-slate-200 dark:text-slate-900"
			>
				{$_('carts.addToCart')}
			</button>
			{#if addErr}<span class="text-red-500">{addErr}</span>{/if}
			{#if someCartDisabled}
				<span class="w-full text-xs text-slate-500">{$_('carts.pickerIncompatibleHint')}</span>
			{/if}
		</div>
	{/if}

	{#if loading}
		<p class="text-sm text-slate-500">{$_('common.loading')}</p>
	{:else if error}
		<p class="text-sm text-red-500">{error}</p>
	{:else if data && data.total === 0}
		<p class="max-w-prose text-sm text-slate-500">{$_('catalog.empty')}</p>
	{:else if data}
		<table class="w-full text-left text-sm">
			<thead class="border-b border-slate-200 text-xs text-slate-500 dark:border-slate-800">
				<tr>
					<th class={th}></th>
					<th class="{th} {sortable}" onclick={() => sortBy('plugin_id')}
						>{$_('catalog.colSource')}{arrow('plugin_id')}</th
					>
					<th class={th}>{$_('catalog.colImage')}</th>
					<th class="{th} {sortable}" onclick={() => sortBy('name')}
						>{$_('catalog.colName')}{arrow('name')}</th
					>
					<th class={th}>{$_('catalog.colTags')}</th>
					<th class="{th} {sortable}" onclick={() => sortBy('price_original')}
						>{$_('catalog.colPriceOriginal')}{arrow('price_original')}</th
					>
					<th class="{th} {sortable}" onclick={() => sortBy('price_current')}
						>{$_('catalog.colPriceCurrent')}{arrow('price_current')}</th
					>
					<th class="{th} {sortable}" onclick={() => sortBy('is_available')}
						>{$_('catalog.colAvailability')}{arrow('is_available')}</th
					>
				</tr>
			</thead>
			<tbody>
				{#each data.items as item (item.id)}
					<tr
						class="border-b border-slate-100 dark:border-slate-800/60"
						class:opacity-50={item.removed}
					>
						<td class="py-2 pr-2">
							<input
								type="checkbox"
								checked={selectedIds.includes(item.id)}
								disabled={item.removed}
								onchange={() => toggleSelect(item)}
								aria-label={$_('carts.addToCart')}
							/>
						</td>
						<td class="py-2 pr-4"><SourceTag pluginId={item.plugin_id} link /></td>
						<td class="py-2 pr-4"><ProductThumb src={item.image_url} /></td>
						<td class="py-2 pr-4">
							<ProductCell
								name={item.name}
								url={item.url}
								brand={item.brand}
								category={item.category}
							/>
						</td>
						<td class="py-2 pr-4"><ProductTags tags={item.tags} /></td>
						<td class="py-2 pr-4 text-slate-400" class:line-through={Number(item.discount_pct) > 0}>
							{money(item.price_original, item.currency)}
						</td>
						<td class="py-2 pr-4 font-medium">
							<div>{money(item.price_current, item.currency)}</div>
							<DiscountBadge discountPct={item.discount_pct} />
						</td>
						<td class="py-2 pr-4 text-slate-500">{availability(item)}</td>
					</tr>
				{/each}
			</tbody>
		</table>

		<div class="flex items-center justify-between text-sm text-slate-500">
			<span>{$_('catalog.count', { values: { total: data.total } })}</span>
			<div class="flex items-center gap-3">
				<button
					class="rounded border border-slate-300 px-2 py-1 disabled:opacity-40 dark:border-slate-700"
					onclick={() => go(-1)}
					disabled={pageNum <= 1}
				>
					{$_('catalog.prev')}
				</button>
				<span>{$_('catalog.pageInfo', { values: { page: pageNum, pages } })}</span>
				<button
					class="rounded border border-slate-300 px-2 py-1 disabled:opacity-40 dark:border-slate-700"
					onclick={() => go(1)}
					disabled={pageNum >= pages}
				>
					{$_('catalog.next')}
				</button>
			</div>
		</div>
	{/if}
</section>
