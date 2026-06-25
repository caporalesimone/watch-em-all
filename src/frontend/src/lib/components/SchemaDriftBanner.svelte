<script lang="ts">
	// 4.F0 — dev schema-drift notice, ADMIN-ONLY. Reads the drift the layout pulled
	// from GET /api/health and renders it through the generic <Banner>; a top-right
	// "Copy Message" button copies it as a JSON {type, title, description}.
	import { onDestroy } from 'svelte';

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

	let copied = $state(false);
	let timer: ReturnType<typeof setTimeout> | undefined;

	function describe(item: SchemaDriftItem): string {
		return item.missing_table
			? $_('schemaDrift.missingTable', { values: { table: item.table } })
			: $_('schemaDrift.missingColumns', {
					values: { table: item.table, columns: item.missing_columns.join(', ') }
				});
	}

	async function copyMessage(): Promise<void> {
		const payload = {
			type: 'error',
			title: 'Database schema drift',
			description: [$_('schemaDrift.intro'), ...$schemaDrift.map(describe)].join('\n')
		};
		try {
			await navigator.clipboard.writeText(JSON.stringify(payload, null, 2));
			copied = true;
			if (timer) clearTimeout(timer);
			timer = setTimeout(() => (copied = false), 5000);
		} catch {
			// Clipboard unavailable (e.g. a non-secure context) — nothing to do.
		}
	}

	onDestroy(() => {
		if (timer) clearTimeout(timer);
	});
</script>

{#if show}
	<button
		type="button"
		onclick={copyMessage}
		class="fixed top-2 right-2 z-50 inline-flex items-center gap-2 rounded border border-red-800 bg-red-600/90 px-3 py-1.5 text-sm font-medium text-white shadow hover:bg-red-700"
	>
		<svg
			class="h-4 w-4 shrink-0"
			viewBox="0 0 24 24"
			fill="none"
			stroke="currentColor"
			stroke-width="2"
			stroke-linecap="round"
			stroke-linejoin="round"
			aria-hidden="true"
		>
			<rect x="9" y="9" width="11" height="11" rx="2" />
			<path d="M5 15V5a2 2 0 0 1 2-2h10" />
		</svg>
		<!-- Both labels live in one grid cell so the button never resizes on toggle. -->
		<span class="grid">
			<span class="col-start-1 row-start-1 whitespace-nowrap"
				>{copied ? $_('schemaDrift.copied') : $_('schemaDrift.copy')}</span
			>
			<span class="invisible col-start-1 row-start-1 whitespace-nowrap" aria-hidden="true"
				>{copied ? $_('schemaDrift.copy') : $_('schemaDrift.copied')}</span
			>
		</span>
	</button>

	<Banner variant="error" icon="⚠️" title={$_('schemaDrift.title')} sidebarOffset>
		<p>{$_('schemaDrift.intro')}</p>
		<ul class="mt-1 list-disc pl-5">
			{#each $schemaDrift as item (item.table)}
				<li><code>{describe(item)}</code></li>
			{/each}
		</ul>
	</Banner>
{/if}
