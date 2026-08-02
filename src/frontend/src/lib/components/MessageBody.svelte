<!--
	A text notification, rendered (10.F10). Admin messages and core-generated ones share one
	payload and one presentation — the category is a badge, not a different page.

	The HTML comes from the server, already sanitised by the core helper the email uses. That is
	the whole reason `{@html}` is safe here, and it is also why there is no markdown-it in this
	bundle: 9.F8 had to undo exactly this shape once, with the Difference rule living in Python
	for the email and in TypeScript for the page until the two drifted. One renderer, one story.
	`body_html` missing (an old row, or a body that failed to render) falls back to the raw text
	with its line breaks kept — degraded, never blank.
-->
<script lang="ts">
	import type { TextMessagePayload } from '$lib/api/client';

	let { payload }: { payload: TextMessagePayload } = $props();
</script>

<article class="max-w-prose space-y-3">
	<h2 class="text-lg font-semibold">{payload.title}</h2>
	{#if payload.body_html}
		<div class="message-body text-sm">
			<!-- eslint-disable-next-line svelte/no-at-html-tags -- sanitised server-side (10.B14) -->
			{@html payload.body_html}
		</div>
	{:else}
		<p class="text-sm whitespace-pre-wrap">{payload.body}</p>
	{/if}
</article>

<style>
	/* The allow-list the core sanitiser permits, and nothing else needs styling. Scoped
	   :global because the markup arrives as a string and carries no Svelte scope class. */
	.message-body :global(p) {
		margin: 0 0 0.75rem;
	}
	.message-body :global(ul),
	.message-body :global(ol) {
		margin: 0 0 0.75rem 1.25rem;
		list-style: revert;
	}
	.message-body :global(a) {
		text-decoration: underline;
	}
	.message-body :global(code) {
		font-family: ui-monospace, monospace;
		font-size: 0.875em;
	}
	.message-body :global(blockquote) {
		border-left: 3px solid currentColor;
		opacity: 0.7;
		padding-left: 0.75rem;
	}
</style>
