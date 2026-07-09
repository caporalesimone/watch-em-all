<script lang="ts">
	import { apiFetch } from '$lib/auth/manager';
	import { _ } from '$lib/i18n';
	import { onMount } from 'svelte';

	type GenProduct = {
		id: number;
		name: string;
		price_current: number | string;
		price_original: number | string | null;
		currency: string;
		is_available: boolean;
		image_url: string | null;
		tags: string[];
	};

	const CURRENCIES = ['EUR', 'USD', 'GBP', 'CHF'];
	const BASE = '/api/plugins/tp-scraper/products';

	let products = $state<GenProduct[]>([]);
	let currency = $state('EUR');
	let busy = $state(false);
	let failed = $state(false);

	function money(value: number | string, ccy: string): string {
		return `${Number(value).toFixed(2)} ${ccy}`;
	}

	async function load(): Promise<void> {
		try {
			const res = await apiFetch(BASE);
			products = (await res.json()) as GenProduct[];
		} catch {
			failed = true;
		}
	}

	async function add(): Promise<void> {
		busy = true;
		failed = false;
		try {
			await apiFetch(BASE, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ currency })
			});
			await load();
		} catch {
			failed = true;
		} finally {
			busy = false;
		}
	}

	async function remove(id: number): Promise<void> {
		busy = true;
		failed = false;
		try {
			await apiFetch(`${BASE}/${id}`, { method: 'DELETE' });
			await load();
		} catch {
			failed = true;
		} finally {
			busy = false;
		}
	}

	async function clearAll(): Promise<void> {
		busy = true;
		failed = false;
		try {
			await apiFetch(BASE, { method: 'DELETE' });
			await load();
		} catch {
			failed = true;
		} finally {
			busy = false;
		}
	}

	onMount(load);
</script>

<section class="space-y-4">
	<h1 class="text-xl font-semibold">{$_('tp_scraper.title')}</h1>
	<p class="max-w-prose text-sm text-slate-500">{$_('tp_scraper.blurb')}</p>

	<div class="flex flex-wrap items-center gap-2">
		<label class="text-sm text-slate-500" for="tp-currency">{$_('tp_scraper.currency')}</label>
		<select
			id="tp-currency"
			bind:value={currency}
			disabled={busy}
			class="rounded border border-slate-300 bg-white px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-900"
		>
			{#each CURRENCIES as ccy (ccy)}
				<option value={ccy}>{ccy}</option>
			{/each}
		</select>
		<button
			class="rounded bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
			onclick={add}
			disabled={busy}
		>
			{$_('tp_scraper.add')}
		</button>
		{#if products.length > 0}
			<button
				class="rounded bg-slate-200 px-3 py-2 text-sm hover:bg-slate-300 disabled:opacity-50 dark:bg-slate-800 dark:hover:bg-slate-700"
				onclick={clearAll}
				disabled={busy}
			>
				{$_('tp_scraper.clearAll')}
			</button>
		{/if}
	</div>

	{#if failed}
		<p class="text-sm text-red-500">{$_('tp_scraper.error')}</p>
	{/if}

	<h2 class="pt-2 text-sm font-semibold text-slate-600 dark:text-slate-300">
		{$_('tp_scraper.generated')} ({products.length})
	</h2>

	{#if products.length === 0}
		<p class="text-sm text-slate-400">{$_('tp_scraper.empty')}</p>
	{:else}
		<ul class="space-y-2">
			{#each products as p (p.id)}
				<li
					class="flex items-center gap-3 rounded border border-slate-200 p-2 dark:border-slate-800"
				>
					{#if p.image_url}
						<img src={p.image_url} alt="" class="h-12 w-12 rounded object-cover" />
					{/if}
					<div class="min-w-0 flex-1">
						<p class="truncate text-sm font-medium">{p.name}</p>
						<p class="text-xs text-slate-500">
							{money(p.price_current, p.currency)}
							{#if p.price_original && Number(p.price_original) > Number(p.price_current)}
								<span class="text-slate-400 line-through">
									{money(p.price_original, p.currency)}
								</span>
							{/if}
							·
							<span class={p.is_available ? 'text-emerald-600' : 'text-amber-600'}>
								{p.is_available ? $_('tp_scraper.available') : $_('tp_scraper.unavailable')}
							</span>
						</p>
						{#if p.tags.length > 0}
							<p class="truncate text-xs text-slate-400">{p.tags.join(' · ')}</p>
						{/if}
					</div>
					<button
						class="rounded px-2 py-1 text-xs text-red-600 hover:bg-red-50 disabled:opacity-50 dark:hover:bg-red-950"
						onclick={() => remove(p.id)}
						disabled={busy}
					>
						{$_('tp_scraper.remove')}
					</button>
				</li>
			{/each}
		</ul>
	{/if}
</section>
