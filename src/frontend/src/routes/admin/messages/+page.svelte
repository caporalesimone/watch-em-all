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
		getAdminMessage,
		listAdminMessages,
		listUsers,
		previewMessage,
		sendAdminMessage,
		type AdminMessageDetail,
		type AdminMessageSummary,
		type AdminUser
	} from '$lib/api/client';
	import DeliveryList from '$lib/components/DeliveryList.svelte';
	import MessageBody from '$lib/components/MessageBody.svelte';
	import PageTitle from '$lib/components/PageTitle.svelte';

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
	let openId = $state<number | null>(null);
	let detail = $state<AdminMessageDetail | null>(null);

	let sending = $state(false);
	let error = $state<string | null>(null);
	let confirmation = $state<string | null>(null);

	// Only accounts that can still sign in: a message to someone locked out is an inbox nobody
	// will open, which is the same rule the broadcast applies on the server.
	const targets = $derived(users.filter((u) => u.is_active && !u.deletion_marked_at));
	const canSend = $derived(
		title.trim().length > 0 &&
			body.trim().length > 0 &&
			!sending &&
			(audience === 'all' || targetId !== null)
	);

	async function refresh(): Promise<void> {
		sent = (await listAdminMessages()).items;
	}

	onMount(() => {
		void refresh();
		void listUsers().then((u) => (users = u));
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
		if (!confirm(question)) return;

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

	async function toggle(id: number): Promise<void> {
		if (openId === id) {
			openId = null;
			return;
		}
		openId = id;
		detail = null;
		detail = await getAdminMessage(id);
	}

	function fmt(iso: string): string {
		return new Date(iso).toLocaleString();
	}

	// Written as literals so the i18n gate sees the keys used.
	const OUTCOME_LABEL: Record<string, string> = {
		delivered: 'admin.messages.outDelivered',
		pending: 'admin.messages.outPending',
		failed: 'admin.messages.outFailed',
		skipped: 'admin.messages.outSkipped'
	};
	function outcomeClass(key: string): string {
		if (key === 'delivered')
			return 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300';
		if (key === 'failed') return 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300';
		return 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400';
	}
</script>

<section class="space-y-8">
	<PageTitle title={$_('admin.messages.title')} />

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

		{#if sent.length === 0}
			<p class="max-w-prose text-sm text-slate-500">{$_('admin.messages.noneSent')}</p>
		{:else}
			<ul class="divide-y divide-slate-100 text-sm dark:divide-slate-800/60">
				{#each sent as m (m.id)}
					<li>
						<button
							onclick={() => toggle(m.id)}
							class="flex w-full flex-wrap items-center gap-3 py-3 text-left hover:bg-slate-50 dark:hover:bg-slate-900/40"
						>
							<span class="w-44 shrink-0 text-xs text-slate-400">{fmt(m.created_at)}</span>
							<span class="w-32 shrink-0 text-xs text-slate-500">
								{m.audience === 'all'
									? $_('admin.messages.toAll', { values: { count: m.recipient_count } })
									: (m.target_username ?? '—')}
							</span>
							<span class="flex-1 truncate font-medium">{m.title}</span>
							{#each Object.entries(m.outcomes).filter(([, n]) => n > 0) as [key, n] (key)}
								<span class="rounded px-1.5 py-0.5 text-xs {outcomeClass(key)}">
									{n}
									{$_(OUTCOME_LABEL[key] ?? key)}
								</span>
							{/each}
						</button>

						{#if openId === m.id}
							<div class="space-y-4 border-t border-slate-100 py-3 pl-4 dark:border-slate-800/60">
								<MessageBody text={m.body} />
								{#if detail}
									<div class="space-y-3">
										<h3 class="text-xs font-medium text-slate-500">
											{$_('admin.messages.recipients')}
										</h3>
										{#each detail.recipients as r (r.user_id)}
											<div class="space-y-1">
												<p class="text-xs font-medium">{r.username}</p>
												<DeliveryList deliveries={r.channels} heading={false} />
											</div>
										{/each}
									</div>
								{:else}
									<p class="text-xs text-slate-500">{$_('common.loading')}</p>
								{/if}
							</div>
						{/if}
					</li>
				{/each}
			</ul>
		{/if}
	</div>
</section>
