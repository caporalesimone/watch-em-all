<!--
	Reading a message, in one place for everybody (10.F19).

	Before this, the same content was reached two different ways: the user navigated to a page,
	the admin expanded a table row. Two layouts for one thing, and the admin's had no way to show
	the message the way its recipient actually sees it. Now both open this.

	A derived popup in the sense 10.T2 intended: it owns *what a message looks like* — the letter,
	the date, the rendered body, whatever belongs underneath — and nothing about how a popup
	behaves, which is all inherited from `Modal`.
-->
<script lang="ts">
	import type { Snippet } from 'svelte';
	import { _ } from 'svelte-i18n';

	import MessageBody from '$lib/components/MessageBody.svelte';
	import Modal from '$lib/components/Modal.svelte';

	let {
		open = $bindable(false),
		title,
		receivedAt,
		bodyHtml = null,
		bodyText,
		loading = false,
		onclose,
		extra
	}: {
		open?: boolean;
		title: string;
		/** ISO timestamp, shown small above the body. */
		receivedAt: string;
		bodyHtml?: string | null;
		bodyText: string;
		loading?: boolean;
		onclose?: () => void;
		/** Whatever belongs under the message: delivery outcomes, recipients. */
		extra?: Snippet;
	} = $props();

	function fmt(iso: string): string {
		return new Date(iso).toLocaleString();
	}
</script>

<Modal bind:open {title} icon="✉️" size="lg" closeLabel={$_('common.close')} {onclose}>
	<div class="space-y-4">
		<p class="text-xs text-slate-400">{fmt(receivedAt)}</p>

		{#if loading}
			<p class="text-sm text-slate-500">{$_('common.loading')}</p>
		{:else}
			<!-- No title inside: the message's own title is the popup's heading, and printing it
			     twice is the sort of thing a shared component quietly does if nobody looks. -->
			<MessageBody html={bodyHtml} text={bodyText} />
		{/if}

		{#if extra}
			<div class="border-t border-slate-200 pt-4 dark:border-slate-800">
				{@render extra()}
			</div>
		{/if}
	</div>
</Modal>
