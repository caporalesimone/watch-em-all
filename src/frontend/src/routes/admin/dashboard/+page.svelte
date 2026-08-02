<script lang="ts">
	// Admin dashboard (10.F7). Two kinds of number that must not be read the same way: what
	// the installation *is* right now, and what it *did* over a window. Every windowed figure
	// carries its window, because a count of deliveries without a period means nothing.
	import { onMount } from 'svelte';
	import { _ } from 'svelte-i18n';

	import { getDashboard, type DashboardResponse } from '$lib/api/client';
	import PageTitle from '$lib/components/PageTitle.svelte';

	let data = $state<DashboardResponse | null>(null);
	let windowDays = $state(7);
	let loading = $state(true);

	async function refresh(): Promise<void> {
		data = await getDashboard(windowDays);
		loading = false;
	}

	onMount(() => void refresh());

	function setWindow(days: number): void {
		windowDays = days;
		void refresh();
	}

	const windows = $derived([
		{ days: 7, label: $_('admin.dashboard.window7') },
		{ days: 30, label: $_('admin.dashboard.window30') }
	]);

	const card = 'rounded-lg border border-slate-200 p-4 dark:border-slate-800';
	const figure = 'text-2xl font-semibold text-slate-800 dark:text-slate-100';
	const caption = 'text-xs text-slate-500';
</script>

<section class="space-y-6">
	<PageTitle title={$_('admin.dashboard.title')} />

	{#if loading || !data}
		<p class="text-sm text-slate-500">{$_('common.loading')}</p>
	{:else}
		<div class="space-y-3">
			<h2 class="text-sm font-medium text-slate-600 dark:text-slate-300">
				{$_('admin.dashboard.totalsTitle')}
			</h2>
			<div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
				<div class={card}>
					<p class={figure}>{data.totals.users_total}</p>
					<p class={caption}>{$_('admin.dashboard.usersTotal')}</p>
					<!--
						Spelled out under the total rather than shown as three slices of it: an
						account being deleted is also inactive, so the parts legitimately overlap
						and a pie would be a lie.
					-->
					<p class="mt-1 text-xs text-slate-400">
						{data.totals.users_active}
						{$_('admin.dashboard.usersActive')} · {data.totals.users_deleting}
						{$_('admin.dashboard.usersDeleting')}
					</p>
				</div>
				<div class={card}>
					<p class={figure}>{data.totals.products_total}</p>
					<p class={caption}>{$_('admin.dashboard.products')}</p>
					<p class="mt-1 text-xs text-slate-400">
						{data.totals.products_delisted}
						{$_('admin.dashboard.productsDelisted')}
					</p>
				</div>
				<div class={card}>
					<p class={figure}>{data.totals.carts_total}</p>
					<p class={caption}>{$_('admin.dashboard.carts')}</p>
				</div>
				<div class={card}>
					<p class={figure}>{data.totals.price_history_rows}</p>
					<p class={caption}>{$_('admin.dashboard.history')}</p>
					<p class="mt-1 text-xs text-slate-400">{$_('admin.dashboard.historyNote')}</p>
				</div>
			</div>
		</div>

		<div class="space-y-3">
			<div class="flex items-center gap-3">
				<h2 class="text-sm font-medium text-slate-600 dark:text-slate-300">
					{$_('admin.dashboard.notificationsTitle')}
				</h2>
				<div class="flex gap-2 text-xs">
					{#each windows as w (w.days)}
						<button
							type="button"
							onclick={() => setWindow(w.days)}
							class="rounded-full border px-3 py-1 {windowDays === w.days
								? 'border-slate-800 bg-slate-800 text-white dark:border-slate-200 dark:bg-slate-200 dark:text-slate-900'
								: 'border-slate-300 hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800'}"
						>
							{w.label}
						</button>
					{/each}
				</div>
			</div>
			<div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
				<div class={card}>
					<p class={figure}>{data.notifications.alerts}</p>
					<p class={caption}>{$_('admin.dashboard.alerts')}</p>
				</div>
				<div class={card}>
					<p class="{figure} text-green-600 dark:text-green-400">
						{data.notifications.delivered}
					</p>
					<p class={caption}>{$_('admin.dashboard.delivered')}</p>
				</div>
				<div class={card}>
					<p
						class="{figure} {data.notifications.failed > 0 ? 'text-red-600 dark:text-red-400' : ''}"
					>
						{data.notifications.failed}
					</p>
					<p class={caption}>{$_('admin.dashboard.failed')}</p>
				</div>
				<div class={card}>
					<p class={figure}>{data.notifications.skipped}</p>
					<p class={caption}>{$_('admin.dashboard.skipped')}</p>
				</div>
			</div>
			<p class="text-xs text-slate-400">
				{$_('admin.dashboard.windowNote', { values: { days: data.notifications.window_days } })}
			</p>
		</div>
	{/if}
</section>
