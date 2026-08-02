<script lang="ts">
	import { onMount } from 'svelte';
	import { _ } from 'svelte-i18n';

	import {
		deleteAlerts,
		getAlert,
		getBroadcast,
		isTextMessage,
		listAlerts,
		markAlertRead,
		markBroadcastRead,
		notificationCategory,
		type AlertDetail,
		type AlertListItem,
		type AlertPage,
		type TextMessagePayload
	} from '$lib/api/client';
	import DeliveryList from '$lib/components/DeliveryList.svelte';
	import NotifyViewer from '$lib/components/NotifyViewer.svelte';
	import PageTitle from '$lib/components/PageTitle.svelte';
	import { confirmDialog } from '$lib/stores/confirm';
	import { refreshUnread } from '$lib/stores/alerts';

	const PAGE_SIZE = 20;

	let data = $state<AlertPage | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let pageNum = $state(1);

	// Category filter (ALERT-R16). Written as string literals in a $derived array so the i18n
	// gate can see the keys used; a template-built key reads as dead to it.
	let category = $state<'all' | 'system' | 'admin'>('all');
	const CATEGORIES = $derived([
		{ value: 'all' as const, label: $_('alerts.categoryAll') },
		{ value: 'system' as const, label: $_('alerts.categorySystem') },
		{ value: 'admin' as const, label: $_('alerts.categoryAdmin') }
	]);

	// Multi-select for bulk delete (ids may span pages).
	let selectedIds = $state<number[]>([]);
	let deleting = $state(false);
	let deleteErr = $state<string | null>(null);

	const pages = $derived(data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1);
	// Announcements are shared rows, so nobody deletes them from their own history — only the
	// user's own notifications are selectable, and "select all" means all of those.
	const deletable = $derived(data ? data.items.filter((a) => a.source === 'alert') : []);
	const allOnPageSelected = $derived(
		deletable.length > 0 && deletable.every((a) => selectedIds.includes(a.id))
	);

	async function load(): Promise<void> {
		loading = true;
		error = null;
		try {
			data = await listAlerts({
				page: pageNum,
				page_size: PAGE_SIZE,
				category: category === 'all' ? undefined : category
			});
		} catch {
			error = $_('alerts.error');
		} finally {
			loading = false;
		}
	}

	function setCategory(next: 'all' | 'system' | 'admin'): void {
		if (next === category) return;
		category = next;
		pageNum = 1; // a narrower list has fewer pages; page 3 of it may not exist
		void load();
	}

	// Where a row leads: the two sources have independent id spaces, so the id alone is not
	// enough to open a notification.
	function href(a: AlertListItem): string {
		return a.source === 'broadcast' ? `/alerts/broadcast/${a.id}` : `/alerts/${a.id}`;
	}

	// A **text** message opens in the popup (10.F19); a digest still gets its own page. The
	// unification Simone asked for is between the two places that show the same thing — the
	// user's history and the admin's sent list — and a digest is not that thing: it is a table
	// of carts, products and prices that a centred dialog would squeeze rather than present.
	const opensInPopup = (a: AlertListItem): boolean => a.title !== null;

	let viewer = $state<AlertDetail | null>(null);
	let viewerOpen = $state(false);
	let viewerLoading = $state(false);

	async function openMessage(a: AlertListItem): Promise<void> {
		viewerOpen = true;
		viewerLoading = true;
		viewer = null;
		try {
			viewer = a.source === 'broadcast' ? await getBroadcast(a.id) : await getAlert(a.id);
			if (!viewer.read) {
				try {
					await (a.source === 'broadcast' ? markBroadcastRead(a.id) : markAlertRead(a.id));
				} catch {
					/* marking read is best-effort — never block the reading on it */
				}
				await load(); // the row (and any older announcement) is read now
				void refreshUnread();
			}
		} catch {
			viewerOpen = false;
			error = $_('alerts.detailError');
		} finally {
			viewerLoading = false;
		}
	}

	// The popup shows a text message, so the payload is that shape; the guard keeps TypeScript
	// honest about the union rather than casting it away.
	const shown = $derived<TextMessagePayload | null>(
		viewer && isTextMessage(viewer.payload) ? viewer.payload : null
	);

	function rowClass(a: AlertListItem): string {
		const base = 'flex flex-1 items-center gap-3 py-3 text-left';
		return a.read ? `${base} text-slate-400 dark:text-slate-500` : base;
	}

	// What the row says at a glance: a text message shows its title, a digest its cart count.
	function preview(a: AlertListItem): string {
		return a.title ?? $_('alerts.summary', { values: { count: a.cart_count } });
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
		const pageIds = deletable.map((a) => a.id);
		selectedIds = allOnPageSelected
			? selectedIds.filter((id) => !pageIds.includes(id))
			: [...new Set([...selectedIds, ...pageIds])];
	}

	async function removeSelected(): Promise<void> {
		if (selectedIds.length === 0) return;
		const ok = await confirmDialog({
			title: $_('alerts.delete'),
			message: $_('alerts.deleteConfirm', { values: { count: selectedIds.length } }),
			confirmLabel: $_('alerts.delete'),
			danger: true
		});
		if (!ok) return;
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

	<div class="flex flex-wrap gap-2 text-sm">
		{#each CATEGORIES as c (c.value)}
			<button
				onclick={() => setCategory(c.value)}
				class="rounded-full border px-3 py-1 {category === c.value
					? 'border-indigo-500 bg-indigo-50 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300'
					: 'border-slate-300 text-slate-500 dark:border-slate-700'}"
			>
				{c.label}
			</button>
		{/each}
	</div>

	{#if loading}
		<p class="text-sm text-slate-500">{$_('common.loading')}</p>
	{:else if error}
		<p class="text-sm text-red-500">{error}</p>
	{:else if data && data.total === 0}
		<p class="max-w-prose text-sm text-slate-500">{$_('alerts.empty')}</p>
	{:else if data}
		<div class="flex flex-wrap items-center gap-3 text-sm">
			<label class="flex items-center gap-2 text-slate-500">
				<input
					type="checkbox"
					checked={allOnPageSelected}
					disabled={deletable.length === 0}
					onchange={toggleAll}
				/>
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
			{#each data.items as a (`${a.source}-${a.id}`)}
				{@const fromAdmin = notificationCategory(a.kind) === 'admin'}
				<li class="flex items-center gap-3 hover:bg-slate-50 dark:hover:bg-slate-900/40">
					{#if a.source === 'alert'}
						<input
							type="checkbox"
							checked={selectedIds.includes(a.id)}
							onchange={() => toggle(a.id)}
							aria-label={fmt(a.created_at)}
							class="ml-1 shrink-0"
						/>
					{:else}
						<!-- An announcement is one row for everybody: there is nothing here to delete. -->
						<span class="ml-1 w-[13px] shrink-0"></span>
					{/if}
					<!-- Two wrappers, one body. A message opens the popup so it is a real <button>; a
					     digest still navigates so it stays a real <a>, which keeps middle-click and
					     "open in new tab" working. <svelte:element> would have been shorter and
					     would have hidden from Svelte — and from a screen reader — which of the two
					     it is at any moment. -->
					{#if opensInPopup(a)}
						<button onclick={() => openMessage(a)} class={rowClass(a)}>
							{@render rowBody(a, fromAdmin)}
						</button>
					{:else}
						<a href={href(a)} class={rowClass(a)}>
							{@render rowBody(a, fromAdmin)}
						</a>
					{/if}
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

<!-- The row's content, shared by the two wrappers above (10.F19). Read rows step back
     (10.F18): what is still unread has to win the glance, and the dot alone is an 8px
     argument. Dimmed, not hidden — it is still the user's history. -->
{#snippet rowBody(a: AlertListItem, fromAdmin: boolean)}
	<span class="w-2 shrink-0">
		{#if !a.read}
			<span class="block h-2 w-2 rounded-full bg-indigo-500" aria-label={$_('alerts.unread')}
			></span>
		{/if}
	</span>
	<span class="w-44 shrink-0 text-xs text-slate-400">{fmt(a.created_at)}</span>
	{#if fromAdmin}
		<!-- Icon and colour of its own (ADMSG-R3): a message from a person must not read
							     like one more automated digest in the same list. Muted once read, so the
							     badge does not go on shouting after the message has been dealt with. -->
		<span
			class="inline-flex shrink-0 items-center gap-1 rounded px-1.5 py-0.5 text-xs {a.read
				? 'bg-slate-100 text-slate-400 dark:bg-slate-800 dark:text-slate-500'
				: 'bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300'}"
		>
			<span aria-hidden="true">📣</span>
			{$_('alerts.categoryAdmin')}
		</span>
	{/if}
	<span class="truncate text-sm {a.read ? '' : 'font-semibold'}">{preview(a)}</span>
{/snippet}

{#if shown && viewer}
	{@const detail = viewer}
	<NotifyViewer
		bind:open={viewerOpen}
		title={shown.title}
		receivedAt={detail.created_at}
		bodyHtml={shown.body_html ?? null}
		bodyText={shown.body}
		loading={viewerLoading}
	>
		{#snippet extra()}
			<DeliveryList deliveries={detail.deliveries} heading={false} />
		{/snippet}
	</NotifyViewer>
{/if}
