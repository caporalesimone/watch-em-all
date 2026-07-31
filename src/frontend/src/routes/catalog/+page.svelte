<script lang="ts">
	import { onMount } from 'svelte';
	import { _ } from 'svelte-i18n';

	import {
		addCartItems,
		ApiErr,
		emptyCatalog,
		getDelistedSummary,
		listCarts,
		listCatalog,
		removeCatalogProduct,
		removeDelistedProducts,
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
	import { mountedPlugins } from '$lib/stores/plugins';

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

	// --- cleanups (9.F4) ---
	//
	// Deleting a product takes its cart memberships with it (the database cascades) and leaves
	// its price history alone, and a confirmation that does not say so is asking for consent to
	// something the user has not been told. Delete mode exists so that a row-level delete is a
	// decision rather than a mis-click next to the "add to cart" checkbox.
	// One member per kind, not `'delisted' | 'all'` on a shared one: a discriminant has to be a
	// single literal per member or TypeScript cannot narrow to the one that carries the item.
	type Pending = { kind: 'delisted' } | { kind: 'all' } | { kind: 'one'; item: CatalogItem };

	let deleteMode = $state(false);
	let pending = $state<Pending | null>(null);
	let cleaning = $state(false);
	let cleanupMsg = $state<string | null>(null);
	let cleanupErr = $state<string | null>(null);

	// The whole catalog's delisted count, not this page's: the button offers to remove all of
	// them, so a number counted from twenty visible rows would understate what the click does.
	// Counted by the backend, together with how many of them sit in a cart — that second number
	// cannot be worked out from the table, and it is the one the cascade takes away silently.
	let delistedTotal = $state(0);
	let delistedInCarts = $state(0);

	// The scraper's name as a person reads it, resolved from the mounted plugins exactly as
	// `SourceTag` does — so renaming a plugin renames it here too, instead of leaving a
	// `plugin_id` with an underscore in the middle of a sentence.
	function scraperName(pluginId: string): string {
		return $mountedPlugins.find((m) => m.name === pluginId)?.display_name ?? pluginId;
	}

	// The names in the remedy below are shown in bold, which means the sentence is rendered as
	// HTML — and those names come from a scraped page. The message templates are ours and carry
	// the only markup; every interpolated value goes through here first, so a category called
	// `<img onerror=…>` arrives as text. Without this the bolding would be an injection point.
	function escapeHtml(value: string): string {
		return value
			.replaceAll('&', '&amp;')
			.replaceAll('<', '&lt;')
			.replaceAll('>', '&gt;')
			.replaceAll('"', '&quot;')
			.replaceAll("'", '&#39;');
	}

	// What has to be removed for the deletion to stick — or null when there is nothing useful to
	// say. HTML, for the bold names.
	//
	// **Only the categories.** A category is a *group* of products added to the scraper, and
	// naming it tells the user something they cannot work out from this dialog: that a list they
	// set up once keeps delivering this product. A product watched on its own is the opposite —
	// the input's name *is* the product's name, already the heading, so the sentence would read
	// "to delete this product, delete this product". The warning above still says it comes back;
	// this line only exists when it can name where from.
	//
	// The plural is a real case, not a defensive one: a product can arrive from two categories at
	// once (which is why provenance is many-to-many), and naming one of them would promise a
	// result that removing it does not produce. The scraper is named too — a category is not
	// addressable without knowing whose store it is, and its page is where the removal happens.
	const sourceRemedy = $derived.by(() => {
		if (pending === null || pending.kind !== 'one') return null;
		const categories = pending.item.sources.filter((s) => s.kind === 'category');
		if (categories.length === 0) return null;
		const scraper = escapeHtml(scraperName(pending.item.plugin_id));
		if (categories.length > 1) {
			// Each name bolded on its own, not the whole list as one run: the commas are ours.
			const inputs = categories.map((s) => `<strong>${escapeHtml(s.label)}</strong>`).join(', ');
			return $_('catalog.confirmRemedyMany', { values: { inputs, scraper } });
		}
		return $_('catalog.confirmRemedyCategory', {
			values: { input: escapeHtml(categories[0].label), scraper }
		});
	});

	async function loadDelistedTotal(): Promise<void> {
		try {
			const summary = await getDelistedSummary();
			delistedTotal = summary.total;
			delistedInCarts = summary.in_carts;
		} catch {
			delistedTotal = 0; // the button simply offers nothing
			delistedInCarts = 0;
		}
	}

	async function runCleanup(): Promise<void> {
		if (pending === null) return;
		const target = pending;
		cleaning = true;
		cleanupMsg = null;
		cleanupErr = null;
		try {
			const res =
				target.kind === 'delisted'
					? await removeDelistedProducts()
					: target.kind === 'all'
						? await emptyCatalog()
						: await removeCatalogProduct(target.item.id);
			cleanupMsg = $_('catalog.cleanupDone', { values: { count: res.removed } });
			// Anything removed cannot stay selected for a cart, and page 3 of a catalog that just
			// lost most of its rows may no longer exist.
			selectedIds = [];
			selectedPluginById = {};
			if (target.kind !== 'one') pageNum = 1;
			await load(true); // re-reads the delisted count too
			await loadCarts(); // the totals on the cart cards moved with the memberships
		} catch (e) {
			cleanupErr = e instanceof ApiErr ? e.detail : $_('catalog.cleanupError');
		} finally {
			cleaning = false;
			pending = null;
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
			// Every time the table is re-read, so is the count beside the cleanup button. A
			// scrape can delist while this page sits open — that is exactly when someone wants
			// the button — and the retry loop below reloads the table without touching it.
			// Not awaited: the table should not wait on a number in a button label.
			void loadDelistedTotal();
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

	<div class="flex flex-wrap items-center justify-between gap-3">
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

		<!-- Cleanups (9.F4): three intentions, three buttons, each confirmed for what it takes. -->
		<div class="flex flex-wrap items-center gap-2 text-sm">
			<button
				class="rounded border border-slate-300 px-3 py-1 hover:bg-slate-100 disabled:opacity-40 dark:border-slate-700 dark:hover:bg-slate-800"
				disabled={cleaning || delistedTotal === 0}
				onclick={() => (pending = { kind: 'delisted' })}
			>
				{$_('catalog.removeDelisted', { values: { count: delistedTotal } })}
			</button>
			<button
				class="rounded border px-3 py-1 {deleteMode
					? 'border-red-400 bg-red-50 text-red-700 dark:border-red-700 dark:bg-red-950/40 dark:text-red-300'
					: 'border-slate-300 hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800'}"
				aria-pressed={deleteMode}
				onclick={() => (deleteMode = !deleteMode)}
			>
				{deleteMode ? $_('catalog.deleteModeOn') : $_('catalog.deleteMode')}
			</button>
			<button
				class="rounded border border-red-300 px-3 py-1 text-red-600 hover:bg-red-50 disabled:opacity-40 dark:border-red-800 dark:text-red-400 dark:hover:bg-red-950/40"
				disabled={cleaning || (data?.total ?? 0) === 0}
				onclick={() => (pending = { kind: 'all' })}
			>
				{$_('catalog.emptyCatalog')}
			</button>
		</div>
	</div>

	{#if cleanupMsg}<p class="text-sm text-emerald-600">{cleanupMsg}</p>{/if}
	{#if cleanupErr}<p class="text-sm text-red-500">{cleanupErr}</p>{/if}
	{#if deleteMode}
		<p class="text-xs text-slate-500">{$_('catalog.deleteModeHint')}</p>
	{/if}

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
					<th class={th}></th>
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
						<td class="py-2 pr-2 text-right">
							{#if deleteMode}
								<button
									class="mr-2 rounded border border-red-300 px-2 py-0.5 text-xs text-red-600 hover:bg-red-100 dark:border-red-800 dark:text-red-400 dark:hover:bg-red-900/40"
									disabled={cleaning}
									onclick={() => (pending = { kind: 'one', item })}
								>
									{$_('catalog.deleteRow')}
								</button>
							{/if}
							<a
								href={`/price-history?product=${item.id}`}
								title={$_('priceHistory.viewChart')}
								aria-label={$_('priceHistory.viewChart')}
								class="inline-block text-slate-400 hover:text-indigo-500"
							>
								<svg
									xmlns="http://www.w3.org/2000/svg"
									viewBox="0 0 24 24"
									fill="none"
									stroke="currentColor"
									stroke-width="2"
									class="h-4 w-4"
									aria-hidden="true"
								>
									<path d="M3 3v18h18" />
									<path d="m7 14 3-4 4 3 5-6" />
								</svg>
							</a>
						</td>
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

<!--
	One dialog for the three cleanups, each stating what goes with the rows: the price history
	and the cart memberships travel with the product (the database cascades), and emptying the
	catalog leaves the watches alone — so the next scheduled run refills what is still watched.
	Saying that here is the difference between a confirmation and a trap.
-->
{#if pending}
	<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
		<!-- 5% wider than it was (34rem), and the whole gain goes to the picture: the text keeps
		     the measure it had, the image box grows from 7rem to 8.75rem. -->
		<div
			class="w-full max-w-[35.75rem] space-y-4 rounded-lg bg-white p-5 shadow-lg dark:bg-slate-900"
		>
			{#if pending.kind === 'one'}
				<!--
					A single product gets its own shape: the thing being deleted is a *thing*, with
					a picture and a provenance, and the consequences are three facts rather than a
					paragraph. No generic title — the product's name is the heading, with the trash
					beside it; one line less, and the dialog opens on what it is about.
				-->
				<div
					class="flex items-center justify-center gap-2 border-b border-slate-200 pb-3 dark:border-slate-800"
				>
					<svg
						xmlns="http://www.w3.org/2000/svg"
						viewBox="0 0 24 24"
						fill="none"
						stroke="currentColor"
						stroke-width="1.7"
						stroke-linecap="round"
						stroke-linejoin="round"
						class="h-5 w-5 shrink-0 text-red-600"
						aria-hidden="true"
					>
						<path d="M3 6h18" />
						<path d="M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2" />
						<path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
						<path d="M10 11v6M14 11v6" />
					</svg>
					<h3 class="text-base font-semibold text-balance">{pending.item.name}</h3>
				</div>
				<div class="grid grid-cols-[8.75rem_1fr] items-start gap-4 max-[30rem]:grid-cols-1">
					<!--
						A FIXED square whatever the picture is, so the dialog does not change shape
						between a tall book cover and a wide box; `object-contain` keeps the image's
						own proportions inside it, letterboxed against the frame.
					-->
					<div
						class="flex h-[8.75rem] w-[8.75rem] items-center justify-center overflow-hidden rounded-md border border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-800"
					>
						{#if pending.item.image_url}
							<img
								src={pending.item.image_url}
								alt=""
								class="max-h-full max-w-full object-contain"
							/>
						{/if}
					</div>
					<div class="flex min-w-0 flex-col gap-2 text-sm text-slate-500">
						<!--
							Only when it is true: the cascade is worth announcing, a zero is not.
						-->
						{#if pending.item.in_carts > 0}
							<p class="grid grid-cols-[1.1rem_1fr] gap-2">
								<span aria-hidden="true">⚠️</span>
								<span>{$_('catalog.confirmOneInCarts')}</span>
							</p>
						{/if}
						{#if pending.item.sources.length}
							<!--
								The consequence and the remedy each carry their own ⚠️: they are two
								things to do about this deletion, and a reader scanning the marks
								would skip a remedy tucked under the line above it.
							-->
							<p class="grid grid-cols-[1.1rem_1fr] gap-2">
								<span aria-hidden="true">⚠️</span>
								<span>{$_('catalog.confirmComesBackLead')}</span>
							</p>
							{#if sourceRemedy}
								<p class="grid grid-cols-[1.1rem_1fr] gap-2">
									<span aria-hidden="true">⚠️</span>
									<!--
									HTML because the input's and the scraper's names are bold. Safe
									because the template is ours and both values are escaped where
									the sentence is built (`escapeHtml`) — they come off a scraped
									page.
								-->
									<!--
									Three lines, and the breaks live in the message rather than in
									this markup: it stays one sentence a translator can reorder.
									`whitespace-pre-line` turns its \n into the breaks.
								-->
									<span class="whitespace-pre-line">{@html sourceRemedy}</span>
								</p>
							{/if}
						{:else}
							<p class="grid grid-cols-[1.1rem_1fr] gap-2">
								<span aria-hidden="true">ℹ️</span>
								<span>{$_('catalog.confirmNothingBringsItBack')}</span>
							</p>
						{/if}
						<!-- ℹ️, not ⚠️: a caution mark on "your data is safe" teaches the eye to
						     stop reading the marks. Same colour as the rest — it is a fact of
						     equal standing, just not a warning. -->
						<p class="grid grid-cols-[1.1rem_1fr] gap-2">
							<span aria-hidden="true">ℹ️</span>
							<span>{$_('catalog.confirmHistoryKept')}</span>
						</p>
					</div>
				</div>
			{:else}
				<h3 class="text-base font-semibold">
					{pending.kind === 'delisted'
						? $_('catalog.confirmDelistedTitle')
						: $_('catalog.confirmEmptyTitle')}
				</h3>
				<p class="text-sm text-slate-500">
					{pending.kind === 'delisted'
						? $_('catalog.confirmDelistedBody', { values: { count: delistedTotal } })
						: $_('catalog.confirmEmptyBody', { values: { count: data?.total ?? 0 } })}
				</p>
				<p class="text-sm text-slate-500">{$_('catalog.confirmCascade')}</p>
				<!--
					How many carts are about to lose something (C7). The membership cascade is
					silent, and this is the one number the catalog table cannot show: a delisted
					product a user had put in a cart vanishes from it without a word otherwise.
					Said only when it is true, so the dialog does not grow a line saying "0".
				-->
				{#if pending.kind === 'delisted' && delistedInCarts > 0}
					<p class="text-sm text-amber-600 dark:text-amber-400">
						{$_('catalog.confirmDelistedInCarts', { values: { count: delistedInCarts } })}
					</p>
				{/if}
				{#if pending.kind === 'all'}
					<p class="text-sm text-slate-500">{$_('catalog.confirmWatchesSurvive')}</p>
				{/if}
			{/if}
			<div class="flex justify-end gap-2">
				<button
					class="rounded border border-slate-300 px-3 py-1 text-sm hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800"
					onclick={() => (pending = null)}
				>
					{$_('common.cancel')}
				</button>
				<button
					class="rounded bg-red-600 px-3 py-1 text-sm text-white hover:bg-red-500 disabled:opacity-50"
					disabled={cleaning}
					onclick={runCleanup}
				>
					{$_('catalog.confirmAction')}
				</button>
			</div>
		</div>
	</div>
{/if}
