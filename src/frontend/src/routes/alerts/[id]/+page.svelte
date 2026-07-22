<script lang="ts">
	import { page } from '$app/stores';
	import { _ } from 'svelte-i18n';

	import {
		getAlert,
		markAlertRead,
		type AlertDetail,
		type AlertDigestProduct
	} from '$lib/api/client';
	import DiscountBadge from '$lib/components/DiscountBadge.svelte';
	import PageTitle from '$lib/components/PageTitle.svelte';
	import ProductCell from '$lib/components/ProductCell.svelte';
	import SourceTag from '$lib/components/SourceTag.svelte';
	import { money } from '$lib/format';
	import { refreshUnread } from '$lib/stores/alerts';

	const alertId = $derived(Number($page.params.id));

	let detail = $state<AlertDetail | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);

	// Cart-event StrEnum value → i18n key. Referenced as string literals so the i18n
	// gate sees them defined-and-used; unknown events fall back to their raw value.
	const EVENT_LABEL: Record<string, string> = {
		CART_ALL_ON_SALE: 'alerts.eventAllOnSale',
		CART_THRESHOLD_REACHED: 'alerts.eventThresholdReached',
		CART_THRESHOLD_REACHED_PARTIAL: 'alerts.eventThresholdPartial'
	};

	// Product tag (StrEnum value) → i18n label. Rendered as a graphic badge, never as the
	// raw underscore string (AEV-R3). "Good news" tags (on sale / back in stock) read green.
	const TAG_LABEL: Record<string, string> = {
		PRODUCT_ON_SALE: 'alerts.tagOnSale',
		PRODUCT_OFF_SALE: 'alerts.tagOffSale',
		PRODUCT_UNAVAILABLE: 'alerts.tagUnavailable',
		PRODUCT_AVAILABLE_AGAIN: 'alerts.tagAvailableAgain'
	};
	const GOOD_TAGS = new Set(['PRODUCT_ON_SALE', 'PRODUCT_AVAILABLE_AGAIN']);
	function tagClass(tag: string): string {
		return GOOD_TAGS.has(tag)
			? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300'
			: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300';
	}

	async function load(id: number): Promise<void> {
		loading = true;
		error = null;
		try {
			detail = await getAlert(id);
			// Opening a notification marks it read (6.F3), then refresh the sidebar badge.
			if (!detail.read) {
				try {
					await markAlertRead(id);
				} catch {
					/* marking read is best-effort — never block the view on it */
				}
			}
			await refreshUnread();
		} catch {
			error = $_('alerts.detailError');
		} finally {
			loading = false;
		}
	}

	$effect(() => {
		void load(alertId);
	});

	function fmt(iso: string): string {
		return new Date(iso).toLocaleString();
	}

	// The digest carries currency on the products; V1 only ever aggregates one currency
	// per cart, so the first product's is the cart's.
	function cartCurrency(products: AlertDigestProduct[]): string | null {
		return products[0]?.currency ?? null;
	}

	function modeLabel(mode: string): string {
		return mode === 'cross' ? $_('carts.modeCross') : $_('carts.modeSingle');
	}
</script>

<section class="space-y-6">
	<a href="/alerts" class="text-sm text-slate-500 hover:underline">{$_('alerts.back')}</a>

	{#if loading}
		<p class="text-sm text-slate-500">{$_('common.loading')}</p>
	{:else if error || !detail}
		<p class="text-sm text-red-500">{error}</p>
	{:else}
		<PageTitle title={fmt(detail.created_at)} />

		{#if detail.payload.cart_alerts.length === 0}
			<p class="max-w-prose text-sm text-slate-500">{$_('alerts.empty')}</p>
		{:else}
			<div class="space-y-4">
				{#each detail.payload.cart_alerts as cart (cart.cart_id)}
					<div class="space-y-3 rounded-lg border border-slate-200 p-4 dark:border-slate-800">
						<div class="flex flex-wrap items-center gap-2">
							<a href="/carts/{cart.cart_id}" class="text-base font-semibold hover:underline"
								>{cart.cart_name}</a
							>
							<span
								class="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-400 dark:bg-slate-800"
								>{modeLabel(cart.mode)}</span
							>
							{#each cart.cart_events as ev (ev)}
								<span
									class="rounded bg-emerald-100 px-1.5 py-0.5 text-xs text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300"
									>{$_(EVENT_LABEL[ev] ?? ev)}</span
								>
							{/each}
						</div>

						{#if cart.products.length > 0}
							<ul class="space-y-2">
								{#each cart.products as p (p.product_id)}
									<li
										class="flex flex-wrap items-start justify-between gap-2 border-t border-slate-100 pt-2 dark:border-slate-800/60"
									>
										<div class="min-w-0">
											<ProductCell name={p.name} url={p.url} />
											<div class="mt-1 flex flex-wrap items-center gap-2">
												<SourceTag pluginId={p.plugin_id} />
												{#each p.tags as tag (tag)}
													<span class="rounded px-1.5 py-0.5 text-xs {tagClass(tag)}">
														{$_(TAG_LABEL[tag] ?? tag)}
													</span>
												{/each}
											</div>
										</div>
										<div class="shrink-0 text-right text-sm">
											{#if p.price_previous && p.price_previous !== p.price_current}
												<span class="text-slate-400 line-through"
													>{money(p.price_previous, p.currency)}</span
												>
												<span class="mx-1 text-slate-400">→</span>
											{/if}
											<span class="font-medium">{money(p.price_current, p.currency)}</span>
											<DiscountBadge discountPct={p.discount_pct} />
										</div>
									</li>
								{/each}
							</ul>
						{/if}

						<!-- Totals -->
						<div
							class="flex flex-wrap items-baseline gap-x-4 gap-y-1 border-t border-slate-100 pt-2 text-sm dark:border-slate-800/60"
						>
							<span class="text-slate-400">{$_('alerts.totals')}</span>
							{#if cart.totals.full !== cart.totals.discounted}
								<span class="text-slate-400 line-through"
									>{money(cart.totals.full, cartCurrency(cart.products))}</span
								>
							{/if}
							<span>{money(cart.totals.discounted, cartCurrency(cart.products))}</span>
							<span class="font-semibold"
								>{$_('carts.final')}: {money(cart.totals.final, cartCurrency(cart.products))}</span
							>
						</div>

						{#if cart.threshold}
							<div class="border-t border-slate-100 pt-2 text-xs dark:border-slate-800/60">
								<span class="text-slate-500">
									{$_('alerts.threshold')}: {$_('alerts.thresholdTarget')}
									{money(cart.threshold.target, cartCurrency(cart.products))} · {$_(
										'alerts.thresholdCurrent'
									)}
									{money(cart.threshold.current, cartCurrency(cart.products))}
								</span>
								{#if cart.threshold.reached}
									<span
										class="ml-1 rounded bg-amber-100 px-1.5 py-0.5 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300"
										>{cart.threshold.partial
											? $_('alerts.thresholdPartial')
											: $_('alerts.thresholdReached')}</span
									>
								{/if}
								{#if cart.threshold.excluded.length > 0}
									<p class="mt-1 text-slate-400">
										{$_('alerts.excluded', {
											values: { names: cart.threshold.excluded.join(', ') }
										})}
									</p>
								{/if}
							</div>
						{/if}
					</div>
				{/each}
			</div>
		{/if}
	{/if}
</section>
