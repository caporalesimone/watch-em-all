<script lang="ts">
	// Admin-only error feed (4.B0+). Reads the errors the layout pulled from
	// GET /api/admin/errors and stacks one <Banner> card per entry, bottom-right of the
	// content area (detached from the edges, clear of the scrollbar). Each card has a
	// Copy button and a ✕ to dismiss it. Shows only to an admin in the shell.
	import { onDestroy } from 'svelte';

	import type { AdminError } from '$lib/api/client';
	import Banner from '$lib/components/Banner.svelte';
	import { _ } from '$lib/i18n';
	import { adminErrors } from '$lib/stores/adminErrors';
	import { auth } from '$lib/stores/auth';

	const isAdminInShell = $derived(
		$auth.status === 'authed' && $auth.user?.role === 'admin' && !$auth.user?.must_change_password
	);

	// Dismissed sources (session-only; reset on reload). New/undismissed errors show.
	let dismissed = $state<Set<string>>(new Set());
	const visible = $derived(
		isAdminInShell ? $adminErrors.filter((e) => !dismissed.has(e.source)) : []
	);

	function dismiss(source: string): void {
		dismissed = new Set([...dismissed, source]);
	}

	let copiedSource = $state<string | null>(null);
	let timer: ReturnType<typeof setTimeout> | undefined;

	async function copy(err: AdminError): Promise<void> {
		const payload = { type: err.type, title: err.title, description: err.description };
		try {
			await navigator.clipboard.writeText(JSON.stringify(payload, null, 2));
			copiedSource = err.source;
			if (timer) clearTimeout(timer);
			timer = setTimeout(() => (copiedSource = null), 5000);
		} catch {
			// Clipboard unavailable (e.g. a non-secure context) — nothing to do.
		}
	}

	onDestroy(() => {
		if (timer) clearTimeout(timer);
	});
</script>

{#if visible.length > 0}
	<!-- Detached from the edges and clear of the main scrollbar (right-6). -->
	<div class="fixed right-6 bottom-4 left-60 z-50 flex max-h-[60vh] flex-col gap-2 overflow-y-auto">
		{#each visible as err (err.source)}
			<Banner variant={err.type} icon="⚠️" title={err.title} onClose={() => dismiss(err.source)}>
				{#snippet action()}
					<!-- White button so it stands out on any variant colour. -->
					<button
						type="button"
						onclick={() => copy(err)}
						class="inline-flex items-center gap-2 rounded bg-white px-3 py-1.5 text-sm font-medium text-slate-800 shadow hover:bg-slate-100"
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
						<!-- Both labels share one grid cell so the button never resizes on toggle. -->
						<span class="grid">
							<span class="col-start-1 row-start-1 whitespace-nowrap"
								>{copiedSource === err.source
									? $_('adminErrors.copied')
									: $_('adminErrors.copy')}</span
							>
							<span class="invisible col-start-1 row-start-1 whitespace-nowrap" aria-hidden="true"
								>{copiedSource === err.source
									? $_('adminErrors.copy')
									: $_('adminErrors.copied')}</span
							>
						</span>
					</button>
				{/snippet}
				<p class="whitespace-pre-line">{err.description}</p>
			</Banner>
		{/each}
	</div>
{/if}
