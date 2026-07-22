<script lang="ts">
	import { onMount } from 'svelte';
	import { _ } from 'svelte-i18n';

	import { createCart, listCarts, type CartCard, type CartMode } from '$lib/api/client';
	import CartCardView from '$lib/components/CartCard.svelte';
	import PageTitle from '$lib/components/PageTitle.svelte';
	import { mountedPlugins } from '$lib/stores/plugins';

	let carts = $state<CartCard[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	let showCreate = $state(false);
	let name = $state('');
	let mode = $state<CartMode>('cross');
	let scraperId = $state('');
	let creating = $state(false);
	let createError = $state<string | null>(null);

	async function load(): Promise<void> {
		loading = true;
		error = null;
		try {
			carts = await listCarts();
		} catch {
			error = $_('carts.error');
		} finally {
			loading = false;
		}
	}

	// Load on mount. Returning here from a detail page remounts this route component
	// (list and detail are separate routes), so this also refreshes after edit/delete.
	// NB: must be onMount, not afterNavigate — the shell defers mounting page content
	// until auth bootstrap finishes, by which point the initial "enter" navigation has
	// already settled, so afterNavigate's on-mount callback never fires on a full reload.
	onMount(() => {
		void load();
	});

	// Default the store to the first scraper when switching to single-store mode.
	$effect(() => {
		if (mode === 'scraper_specific' && !scraperId && $mountedPlugins.length > 0) {
			scraperId = $mountedPlugins[0].name;
		}
	});

	async function create(event: Event): Promise<void> {
		event.preventDefault();
		const trimmed = name.trim();
		if (!trimmed) return;
		creating = true;
		createError = null;
		try {
			const cart = await createCart(
				mode === 'scraper_specific'
					? { name: trimmed, mode, scraper_id: scraperId }
					: { name: trimmed, mode }
			);
			carts = [cart, ...carts];
			showCreate = false;
			name = '';
			mode = 'cross';
			scraperId = '';
		} catch {
			createError = $_('carts.addError');
		} finally {
			creating = false;
		}
	}
</script>

<section class="space-y-6">
	<div class="flex items-center justify-between">
		<PageTitle title={$_('carts.title')} />
		<button
			class="rounded border border-slate-300 px-3 py-1 text-sm hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800"
			onclick={() => (showCreate = !showCreate)}
		>
			{$_('carts.new')}
		</button>
	</div>

	{#if showCreate}
		<form
			onsubmit={create}
			class="space-y-3 rounded-lg border border-slate-200 p-4 dark:border-slate-800"
		>
			<div class="flex flex-col gap-1">
				<label class="text-xs text-slate-500" for="cart-name">{$_('carts.name')}</label>
				<input
					id="cart-name"
					bind:value={name}
					placeholder={$_('carts.namePlaceholder')}
					class="w-64 rounded border border-slate-300 bg-white px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-900"
				/>
			</div>
			<fieldset class="flex flex-col gap-1">
				<span class="text-xs text-slate-500">{$_('carts.mode')}</span>
				<label class="flex items-center gap-2 text-sm">
					<input type="radio" bind:group={mode} value="cross" />
					<span>{$_('carts.modeCross')}</span>
					<span class="text-xs text-slate-400">— {$_('carts.modeCrossHint')}</span>
				</label>
				<label class="flex items-center gap-2 text-sm">
					<input type="radio" bind:group={mode} value="scraper_specific" />
					<span>{$_('carts.modeSingle')}</span>
					<span class="text-xs text-slate-400">— {$_('carts.modeSingleHint')}</span>
				</label>
			</fieldset>
			{#if mode === 'scraper_specific'}
				<div class="flex flex-col gap-1">
					<label class="text-xs text-slate-500" for="cart-store">{$_('carts.store')}</label>
					<select
						id="cart-store"
						bind:value={scraperId}
						class="w-64 rounded border border-slate-300 bg-white px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-900"
					>
						{#each $mountedPlugins as plugin (plugin.name)}
							<option value={plugin.name}>{plugin.display_name}</option>
						{/each}
					</select>
				</div>
			{/if}
			{#if createError}
				<p class="text-sm text-red-500">{createError}</p>
			{/if}
			<div class="flex gap-2">
				<button
					type="submit"
					disabled={creating || !name.trim()}
					class="rounded bg-slate-800 px-3 py-1 text-sm text-white hover:bg-slate-700 disabled:opacity-50 dark:bg-slate-200 dark:text-slate-900"
				>
					{$_('carts.create')}
				</button>
				<button
					type="button"
					class="rounded border border-slate-300 px-3 py-1 text-sm dark:border-slate-700"
					onclick={() => (showCreate = false)}
				>
					{$_('common.cancel')}
				</button>
			</div>
		</form>
	{/if}

	{#if loading}
		<p class="text-sm text-slate-500">{$_('common.loading')}</p>
	{:else if error}
		<p class="text-sm text-red-500">{error}</p>
	{:else if carts.length === 0}
		<p class="max-w-prose text-sm text-slate-500">{$_('carts.empty')}</p>
	{:else}
		<div class="grid gap-4 md:grid-cols-2">
			{#each carts as cart (cart.id)}
				<CartCardView {cart} />
			{/each}
		</div>
	{/if}
</section>
