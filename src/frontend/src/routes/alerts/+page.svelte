<script lang="ts">
	import { onMount } from 'svelte';
	import { _ } from 'svelte-i18n';

	import { deleteAlerts, listAlerts, type AlertPage } from '$lib/api/client';
	import PageTitle from '$lib/components/PageTitle.svelte';
	import { refreshUnread } from '$lib/stores/alerts';

	const PAGE_SIZE = 20;

	let data = $state<AlertPage | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let pageNum = $state(1);

	// Multi-select for bulk delete (ids may span pages).
	let selectedIds = $state<number[]>([]);
	let deleting = $state(false);
	let deleteErr = $state<string | null>(null);

	const pages = $derived(data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1);
	const allOnPageSelected = $derived(
		!!data && data.items.length > 0 && data.items.every((a) => selectedIds.includes(a.id))
	);

	async function load(): Promise<void> {
		loading = true;
		error = null;
		try {
			data = await listAlerts({ page: pageNum, page_size: PAGE_SIZE });
		} catch {
			error = $_('alerts.error');
		} finally {
			loading = false;
		}
	}

	// onMount, not afterNavigate: the shell defers mounting until auth bootstrap finishes,
	// by which point the initial navigation has already settled (see the carts list).
	onMount(() => {
		void load();
		void refreshUnread();
	});

	function go(delta: number): void {
		const next = pageNum + delta;
		if (next >= 1 && next <= pages) {
			pageNum = next;
			void load();
		}
	}

	function toggle(id: number): void {
		selectedIds = selectedIds.includes(id)
			? selectedIds.filter((x) => x !== id)
			: [...selectedIds, id];
	}

	function toggleAll(): void {
		if (!data) return;
		const pageIds = data.items.map((a) => a.id);
		selectedIds = allOnPageSelected
			? selectedIds.filter((id) => !pageIds.includes(id))
			: [...new Set([...selectedIds, ...pageIds])];
	}

	async function removeSelected(): Promise<void> {
		if (selectedIds.length === 0) return;
		if (!confirm($_('alerts.deleteConfirm', { values: { count: selectedIds.length } }))) return;
		deleting = true;
		deleteErr = null;
		try {
			await deleteAlerts(selectedIds);
			selectedIds = [];
			await load();
			if (pageNum > pages) {
				pageNum = pages; // the last page may have emptied
				await load();
			}
			void refreshUnread(); // deleting unread ones changes the badge
		} catch {
			deleteErr = $_('alerts.deleteError');
		} finally {
			deleting = false;
		}
	}

	function fmt(iso: string): string {
		return new Date(iso).toLocaleString();
	}
</script>

<section class="space-y-6">
	<PageTitle title={$_('alerts.title')} />

	{#if loading}
		<p class="text-sm text-slate-500">{$_('common.loading')}</p>
	{:else if error}
		<p class="text-sm text-red-500">{error}</p>
	{:else if data && data.total === 0}
		<p class="max-w-prose text-sm text-slate-500">{$_('alerts.empty')}</p>
	{:else if data}
		<div class="flex flex-wrap items-center gap-3 text-sm">
			<label class="flex items-center gap-2 text-slate-500">
				<input type="checkbox" checked={allOnPageSelected} onchange={toggleAll} />
				{$_('alerts.selectAll')}
			</label>
			{#if selectedIds.length > 0}
				<span class="text-slate-500"
					>{$_('alerts.selected', { values: { count: selectedIds.length } })}</span
				>
				<button
					onclick={removeSelected}
					disabled={deleting}
					class="rounded bg-red-600 px-3 py-1 text-white hover:bg-red-500 disabled:opacity-50"
				>
					{$_('alerts.delete')} ({selectedIds.length})
				</button>
			{/if}
			{#if deleteErr}<span class="text-red-500">{deleteErr}</span>{/if}
		</div>

		<ul class="divide-y divide-slate-100 dark:divide-slate-800/60">
			{#each data.items as a (a.id)}
				<li class="flex items-center gap-3 hover:bg-slate-50 dark:hover:bg-slate-900/40">
					<input
						type="checkbox"
						checked={selectedIds.includes(a.id)}
						onchange={() => toggle(a.id)}
						aria-label={fmt(a.created_at)}
						class="ml-1 shrink-0"
					/>
					<a href="/alerts/{a.id}" class="flex flex-1 items-center gap-3 py-3">
						<span class="w-2 shrink-0">
							{#if !a.read}
								<span
									class="block h-2 w-2 rounded-full bg-indigo-500"
									aria-label={$_('alerts.unread')}
								></span>
							{/if}
						</span>
						<span class="w-44 shrink-0 text-xs text-slate-400">{fmt(a.created_at)}</span>
						<span class="text-sm {a.read ? '' : 'font-semibold'}"
							>{$_('alerts.summary', { values: { count: a.cart_count } })}</span
						>
					</a>
				</li>
			{/each}
		</ul>

		<div class="flex items-center justify-between text-sm text-slate-500">
			<span>{$_('alerts.count', { values: { total: data.total } })}</span>
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
