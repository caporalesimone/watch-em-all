<script lang="ts">
	// Admin dashboard (10.F7). Two kinds of number that must not be read the same way: what
	// the installation *is* right now, and what it *did* over a window. Every windowed figure
	// carries its window, because a count of deliveries without a period means nothing.
	import { onMount } from 'svelte';
	import { _ } from 'svelte-i18n';

	import {
		getDashboard,
		getDashboardUsers,
		type DashboardResponse,
		type DashboardUsers,
		type UserLoadRow
	} from '$lib/api/client';
	import PageTitle from '$lib/components/PageTitle.svelte';

	let data = $state<DashboardResponse | null>(null);
	// Load by account (10.F8). Same window as the notification block above, so the two are
	// read together rather than as two unrelated periods on one page.
	let load = $state<DashboardUsers | null>(null);
	let windowDays = $state(7);
	let loading = $state(true);

	async function refresh(): Promise<void> {
		[data, load] = await Promise.all([getDashboard(windowDays), getDashboardUsers(windowDays)]);
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

	function personName(row: UserLoadRow): string {
		// A purged account can still own rows in a past run; saying so beats an empty cell.
		return row.username ?? $_('admin.dashboard.deletedUser');
	}

	const card = 'rounded-lg border border-slate-200 p-4 dark:border-slate-800';
	const th = 'py-2 pr-4';
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

		<div class="space-y-3">
			<h2 class="text-sm font-medium text-slate-600 dark:text-slate-300">
				{$_('admin.dashboard.loadTitle')}
			</h2>
			<p class="text-xs text-slate-400">{$_('admin.dashboard.loadNote')}</p>
			{#if !load || load.by_user.length === 0}
				<p class="text-sm text-slate-500">{$_('admin.dashboard.loadEmpty')}</p>
			{:else}
				<table class="w-full text-left text-sm">
					<thead class="border-b border-slate-200 text-xs text-slate-500 dark:border-slate-800">
						<tr>
							<th class={th}>{$_('admin.dashboard.colUser')}</th>
							<th class={th}>{$_('admin.dashboard.colProducts')}</th>
							<th class={th}>{$_('admin.dashboard.colCarts')}</th>
							<th class={th}>{$_('admin.dashboard.colRequests')}</th>
							<th class={th}>{$_('admin.dashboard.colCache')}</th>
						</tr>
					</thead>
					<tbody>
						{#each load.by_user as row (row.user_id)}
							<tr class="border-b border-slate-100 dark:border-slate-800/60">
								<td class="{th} font-medium">{personName(row)}</td>
								<td class={th}>{row.products}</td>
								<td class={th}>{row.carts}</td>
								<td class={th}>{row.http_requests}</td>
								<td class="{th} text-slate-500">{row.cache_hits}</td>
							</tr>
						{/each}
					</tbody>
				</table>

				{#if load.by_user_and_scraper.length > 0}
					<h3 class="pt-2 text-xs font-medium text-slate-500">
						{$_('admin.dashboard.byPairTitle')}
					</h3>
					<table class="w-full text-left text-sm">
						<thead class="border-b border-slate-200 text-xs text-slate-500 dark:border-slate-800">
							<tr>
								<th class={th}>{$_('admin.dashboard.colUser')}</th>
								<th class={th}>{$_('admin.dashboard.colScraper')}</th>
								<th class={th}>{$_('admin.dashboard.colRequests')}</th>
								<th class={th}>{$_('admin.dashboard.colCache')}</th>
							</tr>
						</thead>
						<tbody>
							{#each load.by_user_and_scraper as row (`${row.user_id}:${row.scraper_id}`)}
								<tr class="border-b border-slate-100 dark:border-slate-800/60">
									<td class={th}>{personName(row)}</td>
									<td class={th}>{row.scraper_id}</td>
									<td class={th}>{row.http_requests}</td>
									<td class="{th} text-slate-500">{row.cache_hits}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				{/if}
			{/if}
		</div>
	{/if}
</section>
