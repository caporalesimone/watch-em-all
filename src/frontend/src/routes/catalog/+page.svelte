<script lang="ts">
	import { onMount } from 'svelte';
	import { _ } from 'svelte-i18n';

	import {
		listCatalog,
		type CatalogItem,
		type CatalogPage,
		type CatalogSort
	} from '$lib/api/client';
	import PageTitle from '$lib/components/PageTitle.svelte';
	import { mountedPlugins } from '$lib/stores/plugins';

	const PAGE_SIZE = 20;

	let data = $state<CatalogPage | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);

	let q = $state('');
	let sort = $state<CatalogSort>('last_seen_at');
	let order = $state<'asc' | 'desc'>('desc');
	let pageNum = $state(1);

	// Image hover-zoom: only reveal the enlarged preview after the cursor rests on a
	// thumbnail for HOVER_DELAY_MS, so it doesn't flash while scrolling past rows.
	const HOVER_DELAY_MS = 500;
	let hoveredId = $state<number | null>(null);
	let hoverTimer: ReturnType<typeof setTimeout> | null = null;

	const pages = $derived(data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1);

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

	function source(pluginId: string): { name: string; icon: string | null; route: string | null } {
		const p = $mountedPlugins.find((m) => m.name === pluginId);
		return {
			name: p?.display_name ?? pluginId,
			icon: p?.icon ?? null,
			route: p?.route_base ?? null
		};
	}

	function money(value: string, currency: string): string {
		return currency === 'EUR' ? `€${value}` : `${value} ${currency}`;
	}

	function availability(item: CatalogItem): string {
		if (item.removed) return $_('catalog.removed');
		return item.is_available ? $_('catalog.available') : $_('catalog.unavailable');
	}

	function previewEnter(id: number): void {
		if (hoverTimer) clearTimeout(hoverTimer);
		hoverTimer = setTimeout(() => {
			hoveredId = id;
			hoverTimer = null;
		}, HOVER_DELAY_MS);
	}

	function previewLeave(): void {
		if (hoverTimer) {
			clearTimeout(hoverTimer);
			hoverTimer = null;
		}
		hoveredId = null;
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
					<th class="{th} {sortable}" onclick={() => sortBy('plugin_id')}
						>{$_('catalog.colSource')}{arrow('plugin_id')}</th
					>
					<th class={th}>{$_('catalog.colImage')}</th>
					<th class="{th} {sortable}" onclick={() => sortBy('name')}
						>{$_('catalog.colName')}{arrow('name')}</th
					>
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
					{@const src = source(item.plugin_id)}
					<tr
						class="border-b border-slate-100 dark:border-slate-800/60"
						class:opacity-50={item.removed}
					>
						<td class="py-2 pr-4">
							{#if src.route}
								<a
									href={src.route}
									class="flex items-center gap-2 text-slate-500 hover:text-slate-800 hover:underline dark:hover:text-slate-200"
									title={src.name}
								>
									{#if src.icon}
										<img src={src.icon} alt="" class="h-4 w-4" />
									{/if}
									<span>{src.name}</span>
								</a>
							{:else}
								<span class="flex items-center gap-2 text-slate-500" title={src.name}>
									{#if src.icon}
										<img src={src.icon} alt="" class="h-4 w-4" />
									{/if}
									<span>{src.name}</span>
								</span>
							{/if}
						</td>
						<td class="py-2 pr-4">
							<div
								class="relative inline-block"
								role="presentation"
								onmouseenter={() => previewEnter(item.id)}
								onmouseleave={previewLeave}
							>
								{#if item.image_url}
									<img
										src={item.image_url}
										alt=""
										class="h-10 w-10 rounded border border-slate-200 object-cover dark:border-slate-700"
										loading="lazy"
									/>
									<!-- hover (after a ~500ms intent delay): full image (no crop), capped so it never fills the screen -->
									<div
										class="pointer-events-none absolute left-12 top-0 z-20"
										class:hidden={hoveredId !== item.id}
									>
										<img
											src={item.image_url}
											alt=""
											class="max-h-80 max-w-xs rounded-lg border border-slate-200 bg-white p-1 shadow-xl dark:border-slate-700 dark:bg-slate-900"
										/>
									</div>
								{:else}
									<div
										class="h-10 w-10 rounded border border-slate-200 bg-slate-100 dark:border-slate-700 dark:bg-slate-800"
									></div>
								{/if}
							</div>
						</td>
						<td class="py-2 pr-4">
							<a
								href={item.url}
								target="_blank"
								rel="noopener noreferrer"
								class="font-medium text-sky-700 hover:underline dark:text-sky-400">{item.name}</a
							>
							{#if item.brand}
								<div class="text-xs text-slate-500">
									{#if item.brand.link}
										<a
											href={item.brand.link}
											target="_blank"
											rel="noopener noreferrer"
											class="hover:underline">{item.brand.text}</a
										>
									{:else}
										{item.brand.text}
									{/if}
								</div>
							{/if}
							{#if item.product_properties.length > 0}
								<div class="mt-1 flex flex-wrap gap-1">
									{#each item.product_properties as prop (prop)}
										<span
											class="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600 dark:bg-slate-800 dark:text-slate-300"
											>{prop}</span
										>
									{/each}
								</div>
							{/if}
							{#if item.category.length > 0}
								<div class="mt-1 text-xs text-slate-400">
									{#each item.category as cat, i (cat.text + i)}
										{#if i > 0}<span class="px-1">/</span>{/if}
										{#if cat.link}
											<a
												href={cat.link}
												target="_blank"
												rel="noopener noreferrer"
												class="hover:underline">{cat.text}</a
											>
										{:else}
											{cat.text}
										{/if}
									{/each}
								</div>
							{/if}
						</td>
						<td class="py-2 pr-4 text-slate-400" class:line-through={Number(item.discount_pct) > 0}>
							{money(item.price_original, item.currency)}
						</td>
						<td class="py-2 pr-4 font-medium">
							<div>{money(item.price_current, item.currency)}</div>
							{#if Number(item.discount_pct) > 0}
								<span
									class="mt-0.5 inline-block rounded bg-green-100 px-1.5 py-0.5 text-xs text-green-700 dark:bg-green-900/40 dark:text-green-300"
								>
									-{Math.round(Number(item.discount_pct))}%
								</span>
							{/if}
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
