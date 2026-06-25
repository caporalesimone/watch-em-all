<script lang="ts">
	// 4.F0 — dev schema-drift notice, ADMIN-ONLY. Reads the drift the layout pulled
	// from GET /api/health and renders it through the generic <Banner>. Self-hides
	// unless an admin is in the normal shell AND there is drift, so the bar always
	// sits to the right of the sidebar (never over it) and only the admin sees it.
	import type { SchemaDriftItem } from '$lib/api/client';
	import Banner from '$lib/components/Banner.svelte';
	import { _ } from '$lib/i18n';
	import { auth } from '$lib/stores/auth';
	import { schemaDrift } from '$lib/stores/schemaDrift';

	const show = $derived(
		$auth.status === 'authed' &&
			$auth.user?.role === 'admin' &&
			!$auth.user?.must_change_password &&
			$schemaDrift.length > 0
	);

	function describe(item: SchemaDriftItem): string {
		return item.missing_table
			? $_('schemaDrift.missingTable', { values: { table: item.table } })
			: $_('schemaDrift.missingColumns', {
					values: { table: item.table, columns: item.missing_columns.join(', ') }
				});
	}
</script>

{#if show}
	<Banner variant="error" icon="⚠️" title={$_('schemaDrift.title')} sidebarOffset>
		<p>{$_('schemaDrift.intro')}</p>
		<ul class="mt-1 list-disc pl-5">
			{#each $schemaDrift as item (item.table)}
				<li><code>{describe(item)}</code></li>
			{/each}
		</ul>
	</Banner>
{/if}
