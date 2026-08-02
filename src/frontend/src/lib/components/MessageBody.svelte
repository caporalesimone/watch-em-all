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
	// `title` is optional because the compose editor already has one above the tabs (10.F9);
	// the read views pass it. `html` null means "not rendered" and we fall back to `text`.
	let {
		title = null,
		html = null,
		text
	}: { title?: string | null; html?: string | null; text: string } = $props();
</script>

<article class="max-w-prose space-y-3">
	{#if title}
		<h2 class="text-lg font-semibold">{title}</h2>
	{/if}
	{#if html}
		<div class="message-body text-sm">
			<!-- eslint-disable-next-line svelte/no-at-html-tags -- sanitised server-side (10.B14) -->
			{@html html}
		</div>
	{:else}
		<p class="text-sm whitespace-pre-wrap">{text}</p>
	{/if}
</article>

<style>
	/* The allow-list the core sanitiser permits, and nothing else needs styling. Scoped
	   :global because the markup arrives as a string and carries no Svelte scope class. */
	.message-body :global(p) {
		margin: 0 0 0.75rem;
	}
	/* Headings arrive already demoted to h3–h6 by the core renderer (10.B31), because the page
	   around them owns h1 and h2. Sized here from the message's own text rather than from the
	   page scale, so the largest one a body can produce still reads as a section of a message
	   and not as the title of the screen it is sitting in. */
	.message-body :global(h3),
	.message-body :global(h4),
	.message-body :global(h5),
	.message-body :global(h6) {
		font-weight: 600;
		line-height: 1.3;
		margin: 1.25rem 0 0.5rem;
	}
	.message-body :global(h3) {
		font-size: 1.25em;
	}
	.message-body :global(h4) {
		font-size: 1.1em;
	}
	.message-body :global(h5),
	.message-body :global(h6) {
		font-size: 1em;
	}
	/* No gap above the first line of a message: a body that opens with a heading should start
	   where every other body starts. */
	.message-body :global(h3:first-child),
	.message-body :global(h4:first-child),
	.message-body :global(h5:first-child),
	.message-body :global(h6:first-child) {
		margin-top: 0;
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
