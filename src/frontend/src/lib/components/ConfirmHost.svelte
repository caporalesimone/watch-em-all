<!--
	Renders whatever confirmation is pending (10.T2). Mounted once in the app shell, beside the
	Toaster, so no page has to own a dialog just to ask a question.

	Dismissing counts as "no": Escape, the backdrop and the × all answer false, which is the only
	safe reading of "the user closed the question without answering it".
-->
<script lang="ts">
	import { _ } from 'svelte-i18n';

	import Modal from '$lib/components/Modal.svelte';
	import { pendingConfirm } from '$lib/stores/confirm';
</script>

{#if $pendingConfirm}
	{@const request = $pendingConfirm}
	<Modal
		open={true}
		size="sm"
		title={request.title}
		icon={request.danger ? '⚠️' : '❓'}
		closeLabel={$_('common.cancel')}
		onclose={() => request.resolve(false)}
	>
		<p class="text-sm whitespace-pre-line">{request.message}</p>

		{#snippet actions()}
			<button
				onclick={() => request.resolve(false)}
				class="rounded border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800"
			>
				{$_('common.cancel')}
			</button>
			<button
				onclick={() => request.resolve(true)}
				class="rounded px-3 py-1.5 text-sm text-white {request.danger
					? 'bg-red-600 hover:bg-red-500'
					: 'bg-indigo-600 hover:bg-indigo-500'}"
			>
				{request.confirmLabel}
			</button>
		{/snippet}
	</Modal>
{/if}
