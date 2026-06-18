<script lang="ts">
	import { apiFetch } from '$lib/auth/manager';
	import { _ } from '$lib/i18n';

	let pong = $state<string | null>(null);
	let failed = $state(false);

	async function ping(): Promise<void> {
		failed = false;
		pong = null;
		try {
			const res = await apiFetch('/api/plugins/tp-scraper/ping');
			pong = JSON.stringify(await res.json());
		} catch {
			failed = true;
		}
	}
</script>

<section class="space-y-4">
	<h1 class="text-xl font-semibold">{$_('tp_scraper.title')}</h1>
	<p class="max-w-prose text-sm text-slate-500">{$_('tp_scraper.blurb')}</p>
	<button
		class="rounded bg-slate-200 px-3 py-2 text-sm hover:bg-slate-300 dark:bg-slate-800 dark:hover:bg-slate-700"
		onclick={ping}
	>
		{$_('tp_scraper.ping')}
	</button>
	{#if pong}
		<pre class="rounded bg-slate-100 p-3 text-xs dark:bg-slate-800">{pong}</pre>
	{/if}
	{#if failed}
		<p class="text-sm text-red-500">{$_('tp_scraper.error')}</p>
	{/if}
</section>
