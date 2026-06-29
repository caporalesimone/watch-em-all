<script lang="ts">
	// Tag chips (e.g. "Edizione Limitata", "Pre Order"). Shared widget (phase 5 mini-SDK).
	let { tags }: { tags: string[] } = $props();
</script>

{#if tags.length > 0}
	<div class="flex flex-wrap gap-1">
		{#each tags as tag (tag)}
			<span
				class="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600 dark:bg-slate-800 dark:text-slate-300"
				>{tag}</span
			>
		{/each}
	</div>
{/if}
