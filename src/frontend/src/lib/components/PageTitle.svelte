<script lang="ts">
	// The single page-title object: every in-shell page uses it so the heading
	// looks identical everywhere. Pair it with a `space-y-8` page wrapper for the
	// same title↔content spacing as the Profile page.
	let { title }: { title: string } = $props();
</script>

<h1 class="text-2xl font-semibold">{title}</h1>
