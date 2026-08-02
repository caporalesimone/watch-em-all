<!--
	One announcement (10.F10). A route of its own because a broadcast lives in its own table with
	its own id space: /alerts/7 and /alerts/broadcast/7 are two different notifications, and
	sharing the route would have meant carrying a discriminator in a query string.

	Opening it advances the read pointer, which is **monotone**: this also clears the older
	announcements. That is the accepted shape of storing one row instead of one per person, and
	it is right for announcements — the newest is the one that matters.
-->
<script lang="ts">
	import { page } from '$app/stores';
	import { _ } from 'svelte-i18n';

	import {
		getBroadcast,
		isTextMessage,
		markBroadcastRead,
		type AlertDetail
	} from '$lib/api/client';
	import DeliveryList from '$lib/components/DeliveryList.svelte';
	import MessageBody from '$lib/components/MessageBody.svelte';
	import PageTitle from '$lib/components/PageTitle.svelte';
	import { refreshUnread } from '$lib/stores/alerts';

	const messageId = $derived(Number($page.params.id));

	let detail = $state<AlertDetail | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);

	async function load(id: number): Promise<void> {
		loading = true;
		error = null;
		try {
			detail = await getBroadcast(id);
			if (!detail.read) {
				try {
					await markBroadcastRead(id);
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
		void load(messageId);
	});

	function fmt(iso: string): string {
		return new Date(iso).toLocaleString();
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

		<span
			class="inline-flex items-center gap-1 rounded bg-violet-100 px-1.5 py-0.5 text-xs text-violet-700 dark:bg-violet-900/40 dark:text-violet-300"
		>
			<span aria-hidden="true">📣</span>
			{$_('alerts.categoryAdmin')}
		</span>

		{#if isTextMessage(detail.payload)}
			<MessageBody
				title={detail.payload.title}
				html={detail.payload.body_html ?? null}
				text={detail.payload.body}
			/>
		{/if}

		<DeliveryList deliveries={detail.deliveries} />
	{/if}
</section>
