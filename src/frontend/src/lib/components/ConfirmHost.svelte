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

	/**
	 * Split a message into plain and emphasised runs (`highlight`, see the store).
	 *
	 * A scan rather than a regular expression, because the needles are data: a username is free
	 * text and a formatted date carries dots and slashes, both of which a regex would read as
	 * syntax. Longest first, so a value that contains another one still matches as a whole.
	 */
	function segments(message: string, highlight: string[]): { text: string; bold: boolean }[] {
		const needles = [...new Set(highlight.filter(Boolean))].sort((a, b) => b.length - a.length);
		if (needles.length === 0) return [{ text: message, bold: false }];

		const out: { text: string; bold: boolean }[] = [];
		let plain = '';
		for (let i = 0; i < message.length; ) {
			const hit = needles.find((n) => message.startsWith(n, i));
			if (hit) {
				if (plain) out.push({ text: plain, bold: false });
				out.push({ text: hit, bold: true });
				plain = '';
				i += hit.length;
			} else {
				plain += message[i];
				i += 1;
			}
		}
		if (plain) out.push({ text: plain, bold: false });
		return out;
	}
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
		<!-- The each block is written on one line on purpose: `whitespace-pre-line` keeps newlines,
		     and indenting the template would insert one between every run of text. -->
		<!-- prettier-ignore -->
		<p class="text-sm whitespace-pre-line">{#each segments(request.message, request.highlight ?? []) as part, i (i)}{#if part.bold}<strong class="font-semibold">{part.text}</strong>{:else}{part.text}{/if}{/each}</p>

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
