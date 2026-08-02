<script lang="ts">
	// Composing an admin message (10.F9). Write / Preview tabs rather than a live pane: the
	// preview is rendered by the server, so it is the same HTML the recipients get, and asking
	// for it on a tab switch costs one request instead of one per keystroke (Simone's call,
	// 2026-08-02). There is no markdown-it in this bundle on purpose — see the endpoint.
	//
	// A sent message is immutable (ADMSG-R6): no edit, no recall. So the send is a decision, and
	// the button says who it is going to rather than just "Send".
	import { onMount } from 'svelte';
	import { _ } from 'svelte-i18n';

	import {
		deleteAdminMessage,
		getAdminMessage,
		listAdminMessages,
		listAdminNotifiers,
		listUsers,
		previewMessage,
		sendAdminMessage,
		type AdminMessageDetail,
		type AdminMessageSummary,
		type AdminNotifier,
		type AdminUser
	} from '$lib/api/client';
	import DeliveryList from '$lib/components/DeliveryList.svelte';
	import MessageBody from '$lib/components/MessageBody.svelte';
	import NotifyViewer from '$lib/components/NotifyViewer.svelte';
	import PageTitle from '$lib/components/PageTitle.svelte';
	import SystemMessages from '$lib/components/SystemMessages.svelte';
	import { confirmDialog } from '$lib/stores/confirm';

	// Two things live on this page and they are not the same job: writing to people, and
	// editing what the system writes on its own (10.F11). Two tabs rather than two entries in
	// the sidebar — an admin looking for "the words this installation sends" looks in one place.
	let section = $state<'announcements' | 'system'>('announcements');

	let title = $state('');
	let body = $state('');
	let audience = $state<'all' | 'user'>('all');
	let targetId = $state<number | null>(null);

	let tab = $state<'write' | 'preview'>('write');
	let previewHtml = $state<string | null>(null);
	let previewing = $state(false);
	let previewErr = $state(false);

	let users = $state<AdminUser[]>([]);
	let sent = $state<AdminMessageSummary[]>([]);
	let viewing = $state<AdminMessageSummary | null>(null);
	let viewerOpen = $state(false);
	let viewerHtml = $state<string | null>(null);
	let detail = $state<AdminMessageDetail | null>(null);

	let sending = $state(false);
	let error = $state<string | null>(null);
	let confirmation = $state<string | null>(null);

	// Who can actually receive this: accounts that can still sign in, and **never an admin** —
	// this channel is for the people who use the installation, and whoever administers it
	// already has the logs. Mirrors what the server does; the server is where it is enforced.
	const targets = $derived(
		users.filter((u) => u.is_active && !u.deletion_marked_at && u.role !== 'admin')
	);
	const canSend = $derived(
		title.trim().length > 0 &&
			body.trim().length > 0 &&
			!sending &&
			(audience === 'all' ? targets.length > 0 : targetId !== null)
	);

	// Where this message will actually land (10.F24). The in-app copy always exists (ADMSG-R2),
	// but email is the only channel that leaves the installation, and an admin composing a
	// maintenance notice is entitled to know before pressing Send that nobody will get a mail.
	// Two causes, one consequence, said separately because they are fixed differently: the
	// kill-switch is a click, an incomplete SMTP config is a form.
	let notifiers = $state<AdminNotifier[]>([]);
	const email = $derived(notifiers.find((n) => n.plugin_id === 'email'));
	const emailReach = $derived(
		email === undefined
			? 'none' // no email plugin loaded at all: nothing to warn about
			: !email.enabled
				? 'off'
				: !email.admin_config_complete
					? 'unconfigured'
					: 'ok'
	);

	// The sent list is paged and filterable (10.F30). Both live here rather than in the URL: this
	// is the lower half of a page whose upper half is a draft, and putting the list state in the
	// address bar would make "next page" a navigation that discards what is being written.
	let sentPage = $state(1);
	let sentTotal = $state(0);
	let sentFilter = $state<'all' | 'user' | null>(null);
	const SENT_PAGE_SIZE = 10;
	const sentPages = $derived(Math.max(1, Math.ceil(sentTotal / SENT_PAGE_SIZE)));

	async function refresh(): Promise<void> {
		const got = await listAdminMessages(sentPage, SENT_PAGE_SIZE, sentFilter);
		sent = got.items;
		sentTotal = got.total;
		// Deleting the last row of the last page would otherwise leave an empty list with a page
		// number nobody can get off.
		if (sent.length === 0 && sentPage > 1) {
			sentPage = 1;
			await refresh();
		}
	}

	function setSentFilter(next: 'all' | 'user' | null): void {
		sentFilter = next;
		sentPage = 1;
		void refresh();
	}

	function goSent(delta: number): void {
		sentPage = Math.min(sentPages, Math.max(1, sentPage + delta));
		void refresh();
	}

	// Written out one by one, not built from a prefix: the i18n gate matches literals.
	const sentFilters = $derived([
		{ key: null, label: $_('admin.messages.filterAll') },
		{ key: 'all' as const, label: $_('admin.messages.filterBroadcast') },
		{ key: 'user' as const, label: $_('admin.messages.filterTargeted') }
	]);

	async function removeMessage(m: AdminMessageSummary): Promise<void> {
		// Two different consequences, so two different sentences. For a broadcast this is the
		// only way the announcement ever leaves anybody's history — a recipient cannot delete a
		// row that belongs to everybody — and the confirmation has to say so before the click,
		// not after.
		const key =
			m.audience === 'all'
				? 'admin.messages.confirmDeleteBroadcast'
				: 'admin.messages.confirmDeleteTargeted';
		const who = m.audience === 'all' ? '' : (m.target_username ?? '');
		const ok = await confirmDialog({
			title: $_('admin.messages.deleteTitle'),
			message: $_(key, { values: { title: m.title, username: who } }),
			highlight: [m.title, who].filter(Boolean),
			confirmLabel: $_('admin.messages.deleteTitle'),
			danger: true
		});
		if (!ok) return;
		try {
			await deleteAdminMessage(m.id);
			await refresh();
		} catch {
			error = $_('admin.messages.deleteError');
		}
	}

	onMount(() => {
		void refresh();
		void listUsers().then((u) => (users = u));
		// A banner that fails to load is a banner that stays quiet: the page's job is composing,
		// and a warning about delivery must never be the reason it cannot be used.
		void listAdminNotifiers()
			.then((n) => (notifiers = n))
			.catch(() => undefined);
	});

	async function showPreview(): Promise<void> {
		tab = 'preview';
		// Nothing typed yet: no point asking the server to render an empty string.
		if (!body.trim()) {
			previewHtml = null;
			return;
		}
		previewing = true;
		previewErr = false;
		try {
			previewHtml = await previewMessage(body);
		} catch {
			previewHtml = null;
			previewErr = true;
		} finally {
			previewing = false;
		}
	}

	async function send(): Promise<void> {
		const recipient =
			audience === 'all' ? null : (targets.find((u) => u.id === targetId)?.username ?? '');
		const question =
			audience === 'all'
				? $_('admin.messages.confirmAll', { values: { count: targets.length } })
				: $_('admin.messages.confirmUser', { values: { username: recipient } });
		const ok = await confirmDialog({
			title: $_('admin.messages.compose'),
			message: question,
			confirmLabel: $_('admin.messages.sendOne')
		});
		if (!ok) return;

		sending = true;
		error = null;
		confirmation = null;
		try {
			const result = await sendAdminMessage({
				title: title.trim(),
				body,
				target_user_id: audience === 'all' ? null : targetId
			});
			confirmation = $_('admin.messages.sentTo', {
				values: { count: result.recipient_count }
			});
			title = '';
			body = '';
			previewHtml = null;
			tab = 'write';
			await refresh();
		} catch {
			error = $_('admin.messages.sendError');
		} finally {
			sending = false;
		}
	}

	// The same popup the recipient sees (10.F19), instead of the row expansion this page used
	// to do. The body is rendered through the preview endpoint — the very renderer that produced
	// what was delivered — so the admin reads the message as it actually arrived, not as a
	// second-best approximation of it.
	async function openMessage(m: AdminMessageSummary): Promise<void> {
		viewing = m;
		viewerOpen = true;
		detail = null;
		viewerHtml = null;
		const [full, html] = await Promise.all([
			getAdminMessage(m.id),
			previewMessage(m.body).catch(() => null)
		]);
		detail = full;
		viewerHtml = html;
	}

	function fmt(iso: string): string {
		return new Date(iso).toLocaleString();
	}

	/**
	 * Who a message went to. "Everyone" without a count since 10.F30 (Simone's call): the count
	 * was people while the tags beside it count deliveries, and the two numbers standing next to
	 * each other invited exactly the reading they should not — "Everyone (1)" and "2 delivered"
	 * looked like a contradiction and were both correct.
	 */
	function recipientOf(m: AdminMessageSummary): string {
		return m.audience === 'all' ? $_('admin.messages.toAll') : (m.target_username ?? '—');
	}

	// The per-status tally is gone from the list (10.B30): it counted deliveries, and the only
	// one of them an admin acts on is a failure, which the row still shows. The full breakdown
	// per recipient and per channel is a click away, in the popup, where it belongs.
</script>

<section class="space-y-8">
	<PageTitle title={$_('admin.messages.title')} />

	<div class="flex gap-2 text-sm">
		<button
			onclick={() => (section = 'announcements')}
			class="rounded-full border px-3 py-1 {section === 'announcements'
				? 'border-indigo-500 bg-indigo-50 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300'
				: 'border-slate-300 text-slate-500 dark:border-slate-700'}"
		>
			{$_('admin.messages.sectionAnnouncements')}
		</button>
		<button
			onclick={() => (section = 'system')}
			class="rounded-full border px-3 py-1 {section === 'system'
				? 'border-indigo-500 bg-indigo-50 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300'
				: 'border-slate-300 text-slate-500 dark:border-slate-700'}"
		>
			{$_('admin.messages.sectionSystem')}
		</button>
	</div>

	{#if section === 'system'}
		<SystemMessages />
	{:else}
		{#if emailReach === 'off' || emailReach === 'unconfigured'}
			<div
				class="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200"
			>
				<span>
					{emailReach === 'off'
						? $_('admin.messages.emailOff')
						: $_('admin.messages.emailUnconfigured')}
				</span>
				<a href="/admin/notifiers" class="font-medium underline">
					{$_('admin.messages.emailFix')}
				</a>
			</div>
		{/if}

		<!-- ------------------------------------------------------------------ compose -->
		<div class="space-y-4 rounded-lg border border-slate-200 p-4 dark:border-slate-800">
			<h2 class="text-sm font-medium text-slate-500">{$_('admin.messages.compose')}</h2>

			<div class="flex flex-wrap items-center gap-4 text-sm">
				<label class="flex items-center gap-2">
					<input type="radio" bind:group={audience} value="all" />
					{$_('admin.messages.audienceAll')}
				</label>
				<label class="flex items-center gap-2">
					<input type="radio" bind:group={audience} value="user" />
					{$_('admin.messages.audienceUser')}
				</label>
				{#if audience === 'user'}
					<select
						bind:value={targetId}
						class="rounded border border-slate-300 px-2 py-1 dark:border-slate-700 dark:bg-slate-900"
					>
						<option value={null}>{$_('admin.messages.pickUser')}</option>
						{#each targets as u (u.id)}
							<option value={u.id}>{u.username}</option>
						{/each}
					</select>
				{/if}
			</div>
			<!-- Said out loud so a count lower than the account total does not read as a bug. -->
			<p class="text-xs text-slate-400">{$_('admin.messages.adminsExcluded')}</p>
			{#if audience === 'all' && targets.length === 0}
				<p class="text-xs text-amber-600 dark:text-amber-400">
					{$_('admin.messages.noAudience')}
				</p>
			{/if}

			<label class="block space-y-1 text-sm">
				<span class="text-slate-500">{$_('admin.messages.titleLabel')}</span>
				<input
					bind:value={title}
					maxlength="200"
					class="w-full rounded border border-slate-300 px-2 py-1 dark:border-slate-700 dark:bg-slate-900"
				/>
			</label>

			<div>
				<div class="flex gap-1 border-b border-slate-200 text-sm dark:border-slate-800">
					<button
						onclick={() => (tab = 'write')}
						class="rounded-t px-3 py-1.5 {tab === 'write'
							? 'border border-b-transparent border-slate-200 font-medium dark:border-slate-800'
							: 'text-slate-500'}"
					>
						{$_('admin.messages.tabWrite')}
					</button>
					<button
						onclick={showPreview}
						class="rounded-t px-3 py-1.5 {tab === 'preview'
							? 'border border-b-transparent border-slate-200 font-medium dark:border-slate-800'
							: 'text-slate-500'}"
					>
						{$_('admin.messages.tabPreview')}
					</button>
				</div>

				{#if tab === 'write'}
					<textarea
						bind:value={body}
						rows="14"
						maxlength="20000"
						placeholder={$_('admin.messages.bodyPlaceholder')}
						class="w-full rounded-b border border-slate-300 p-3 font-mono text-sm dark:border-slate-700 dark:bg-slate-900"
					></textarea>
					<p class="mt-1 text-xs text-slate-400">{$_('admin.messages.markdownHint')}</p>
				{:else}
					<div
						class="min-h-[14rem] rounded-b border border-slate-300 p-3 dark:border-slate-700 dark:bg-slate-900"
					>
						{#if previewing}
							<p class="text-sm text-slate-500">{$_('common.loading')}</p>
						{:else if previewErr}
							<p class="text-sm text-red-500">{$_('admin.messages.previewError')}</p>
						{:else if previewHtml}
							<MessageBody html={previewHtml} text={body} />
						{:else}
							<p class="text-sm text-slate-400">{$_('admin.messages.previewEmpty')}</p>
						{/if}
					</div>
					<!-- Said out loud because it is the promise the server-side render buys: this is
				     not an approximation of the message, it is the message. -->
					<p class="mt-1 text-xs text-slate-400">{$_('admin.messages.previewIsExact')}</p>
				{/if}
			</div>

			<div class="flex flex-wrap items-center gap-3">
				<button
					onclick={send}
					disabled={!canSend}
					class="rounded bg-indigo-600 px-4 py-1.5 text-sm text-white hover:bg-indigo-500 disabled:opacity-40"
				>
					{audience === 'all'
						? $_('admin.messages.sendAll', { values: { count: targets.length } })
						: $_('admin.messages.sendOne')}
				</button>
				<span class="text-xs text-slate-400">{$_('admin.messages.immutableHint')}</span>
				{#if confirmation}<span class="text-sm text-emerald-600">{confirmation}</span>{/if}
				{#if error}<span class="text-sm text-red-500">{error}</span>{/if}
			</div>
		</div>

		<!-- ------------------------------------------------------------------- sent -->
		<div class="space-y-3">
			<h2 class="text-sm font-medium text-slate-500">{$_('admin.messages.sentTitle')}</h2>

			<div class="flex flex-wrap gap-2 text-xs">
				{#each sentFilters as chip (chip.label)}
					<button
						type="button"
						onclick={() => setSentFilter(chip.key)}
						class="rounded-full border px-3 py-1 {sentFilter === chip.key
							? 'border-slate-800 bg-slate-800 text-white dark:border-slate-200 dark:bg-slate-200 dark:text-slate-900'
							: 'border-slate-300 hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800'}"
					>
						{chip.label}
					</button>
				{/each}
			</div>

			{#if sent.length === 0}
				<p class="max-w-prose text-sm text-slate-500">{$_('admin.messages.noneSent')}</p>
			{:else}
				<!--
					A real table with headers (10.F30). It was a flex row with a fixed-width recipient
					cell and no truncation, so `simone.caporale@cnh.com` ran straight over the title.
					A table also gives the columns names, which this list needed anyway: a bare date
					and a bare address beside a title do not say what they are.
				-->
				<div class="overflow-x-auto">
					<table class="w-full table-fixed text-left text-sm">
						<thead class="border-b border-slate-200 text-xs text-slate-400 dark:border-slate-800">
							<tr>
								<th class="w-40 py-2 pr-3 font-normal">{$_('admin.messages.colSent')}</th>
								<th class="w-48 py-2 pr-3 font-normal">{$_('admin.messages.colRecipient')}</th>
								<th class="py-2 pr-3 font-normal">{$_('admin.messages.colTitle')}</th>
								<th class="w-44 py-2 pr-3 font-normal">{$_('admin.messages.colReach')}</th>
								<th class="w-20 py-2 font-normal"></th>
							</tr>
						</thead>
						<tbody class="divide-y divide-slate-100 dark:divide-slate-800/60">
							{#each sent as m (m.id)}
								<tr class="align-top hover:bg-slate-50 dark:hover:bg-slate-900/40">
									<td class="py-2 pr-3 text-xs text-slate-400">{fmt(m.created_at)}</td>
									<!-- Truncated, with the whole value on hover: an address is exactly the
									     kind of cell that runs long, and it used to take the title with it. -->
									<td class="truncate py-2 pr-3 text-xs text-slate-500" title={recipientOf(m)}>
										{recipientOf(m)}
									</td>
									<td class="py-2 pr-3">
										<button
											onclick={() => openMessage(m)}
											class="block w-full truncate text-left font-medium hover:underline"
											title={m.title}
										>
											{m.title}
										</button>
									</td>
									<td class="py-2 pr-3">
										<!--
											People, not deliveries (10.B30, Simone's call). The old tags counted
											one per recipient per channel, so a single reader produced "2
											delivered" — arithmetic nobody needed. What an admin wants from a
											sent announcement is how far it went and how much of it landed.

											"Read" is **in-app only**, and that is not a shortcut: an email that
											left the building says nothing about whether anybody looked at it,
											and a number pretending otherwise is worse than no number. It stays
											an aggregate — *who* read it is not the sender's business (ADMSG-R5).
										-->
										<div class="flex flex-wrap items-center gap-1 text-xs">
											<!-- Chips, the same shape the rest of the app uses for a state. The
											     first stays neutral — how far a message went is a fact, not good
											     news — while the second goes green only once somebody has opened
											     it, so a glance down the column finds what actually landed. -->
											<span
												class="rounded bg-slate-100 px-1.5 py-0.5 text-slate-600 dark:bg-slate-800 dark:text-slate-300"
												title={$_('admin.messages.reachedHint')}
											>
												{$_('admin.messages.reached', { values: { n: m.recipient_count } })}
											</span>
											<span
												class="rounded px-1.5 py-0.5 {m.read_count > 0
													? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300'
													: 'bg-slate-100 text-slate-400 dark:bg-slate-800 dark:text-slate-500'}"
												title={$_('admin.messages.readHint')}
											>
												{$_('admin.messages.readCount', { values: { n: m.read_count } })}
											</span>
											<!-- The one delivery fact still worth a tag: a channel that refused is
											     something to act on, unlike a tally of successes. -->
											{#if m.outcomes.failed > 0}
												<span
													class="rounded bg-red-100 px-1.5 py-0.5 text-red-700 dark:bg-red-900/40 dark:text-red-300"
												>
													{m.outcomes.failed}
													{$_('admin.messages.outFailed')}
												</span>
											{/if}
										</div>
									</td>
									<td class="py-2 text-right">
										<button
											type="button"
											onclick={() => removeMessage(m)}
											class="rounded border border-red-300 px-2 py-1 text-xs text-red-600 hover:bg-red-50 dark:border-red-800 dark:text-red-400 dark:hover:bg-red-950/40"
										>
											{$_('admin.messages.deleteTitle')}
										</button>
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>

				<div class="flex items-center justify-between text-sm text-slate-500">
					<span>{$_('admin.messages.sentCount', { values: { total: sentTotal } })}</span>
					<div class="flex items-center gap-3">
						<button
							class="rounded border border-slate-300 px-2 py-1 disabled:opacity-40 dark:border-slate-700"
							onclick={() => goSent(-1)}
							disabled={sentPage <= 1}
						>
							{$_('catalog.prev')}
						</button>
						<span>{$_('catalog.pageInfo', { values: { page: sentPage, pages: sentPages } })}</span>
						<button
							class="rounded border border-slate-300 px-2 py-1 disabled:opacity-40 dark:border-slate-700"
							onclick={() => goSent(1)}
							disabled={sentPage >= sentPages}
						>
							{$_('catalog.next')}
						</button>
					</div>
				</div>
			{/if}
		</div>
	{/if}
</section>

{#if viewing}
	{@const m = viewing}
	<NotifyViewer
		bind:open={viewerOpen}
		title={m.title}
		receivedAt={m.created_at}
		bodyHtml={viewerHtml}
		bodyText={m.body}
		onclose={() => (viewing = null)}
	>
		{#snippet extra()}
			<div class="space-y-3">
				<h3 class="text-xs font-medium text-slate-500">{$_('admin.messages.recipients')}</h3>
				{#if detail}
					{#each detail.recipients as r (r.user_id)}
						<div class="space-y-1">
							<p class="text-xs font-medium">{r.username}</p>
							<DeliveryList deliveries={r.channels} heading={false} />
						</div>
					{/each}
				{:else}
					<p class="text-xs text-slate-500">{$_('common.loading')}</p>
				{/if}
			</div>
		{/snippet}
	</NotifyViewer>
{/if}
