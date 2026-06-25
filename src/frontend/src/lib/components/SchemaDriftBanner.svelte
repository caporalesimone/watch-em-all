<script lang="ts">
	// 4.F0 — dev-only schema-drift banner. Reads the drift the layout pulled from
	// GET /api/health into the store; self-hides when empty (so it never shows in
	// production, where the backend reports null behind WEA_SCHEMA_DRIFT_ALERT).
	import type { SchemaDriftItem } from '$lib/api/client';
	import { _ } from '$lib/i18n';
	import { schemaDrift } from '$lib/stores/schemaDrift';

	function describe(item: SchemaDriftItem): string {
		return item.missing_table
			? $_('schemaDrift.missingTable', { values: { table: item.table } })
			: $_('schemaDrift.missingColumns', {
					values: { table: item.table, columns: item.missing_columns.join(', ') }
				});
	}
</script>

{#if $schemaDrift.length > 0}
	<div
		role="alert"
		class="fixed inset-x-0 bottom-0 z-50 max-h-40 overflow-auto border-t-2 border-red-800 bg-red-600 px-4 py-2 text-sm text-white shadow-lg"
	>
		<p class="font-semibold">⚠️ {$_('schemaDrift.title')}</p>
		<p class="text-red-100">{$_('schemaDrift.intro')}</p>
		<ul class="mt-1 list-disc pl-5">
			{#each $schemaDrift as item (item.table)}
				<li><code>{describe(item)}</code></li>
			{/each}
		</ul>
	</div>
{/if}
