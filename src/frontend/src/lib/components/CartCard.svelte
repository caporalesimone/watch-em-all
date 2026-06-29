<script lang="ts">
	import { _ } from 'svelte-i18n';

	import { deleteCart, patchCart, type CartCard } from '$lib/api/client';

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

	function money(value: string, currency: string | null): string {
		return !currency || currency === 'EUR' ? `€${value}` : `${value} ${currency}`;
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
							draftName = cart.name;
						}}>{$_('common.cancel')}</button
					>
				</div>
			{:else}
				<h3 class="truncate text-base font-semibold">{cart.name}</h3>
			{/if}
			<div class="mt-1 flex flex-wrap items-center gap-x-2 text-xs text-slate-400">
				<span class="rounded bg-slate-100 px-1.5 py-0.5 dark:bg-slate-800">
					{cart.mode === 'cross'
						? $_('carts.modeCross')
						: $_('carts.modeSingle')}{#if cart.scraper_id}
						· {cart.scraper_id}{/if}
				</span>
				<span>{$_('carts.products', { values: { count: cart.member_count } })}</span>
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

	<div class="mt-3 flex flex-wrap items-baseline gap-x-4 gap-y-1 text-sm">
		{#if cart.total_full !== cart.total_discounted}
			<span class="text-slate-400 line-through">{money(cart.total_full, cart.currency)}</span>
		{/if}
		<span>{money(cart.total_discounted, cart.currency)}</span>
		<span class="font-semibold">{$_('carts.final')}: {money(cart.final_price, cart.currency)}</span>
	</div>
</div>
