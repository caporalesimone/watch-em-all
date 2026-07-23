<script lang="ts">
	// Debug page (phase 7): quick links to the dev tooling (Mailpit, Swagger, the DB browser…),
	// for user and admin alike. TEMPORARY — to be hidden/removed before v1. The external tools
	// exist only in the dev stack; links are built against the current host so remote dev works.
	import { onMount } from 'svelte';
	import { _ } from 'svelte-i18n';

	import PageTitle from '$lib/components/PageTitle.svelte';

	let host = $state('localhost');
	onMount(() => {
		host = window.location.hostname || 'localhost';
	});

	const tools = $derived([
		{ label: 'debug.swagger', desc: 'debug.swaggerDesc', href: '/api/docs' },
		{ label: 'debug.mailpit', desc: 'debug.mailpitDesc', href: `http://${host}:8025` },
		{ label: 'debug.pgweb', desc: 'debug.pgwebDesc', href: `http://${host}:8081` },
		{ label: 'debug.health', desc: 'debug.healthDesc', href: '/api/health' }
	]);
</script>

<section class="max-w-2xl space-y-6">
	<PageTitle title={$_('debug.title')} />
	<p class="text-sm text-slate-500 dark:text-slate-400">{$_('debug.subtitle')}</p>

	<ul class="space-y-3">
		{#each tools as t (t.href)}
			<li class="rounded-lg border border-slate-200 p-4 dark:border-slate-800">
				<a
					href={t.href}
					target="_blank"
					rel="noopener"
					class="font-medium text-indigo-600 hover:underline dark:text-indigo-400"
				>
					{$_(t.label)} ↗
				</a>
				<p class="mt-1 text-sm text-slate-500 dark:text-slate-400">{$_(t.desc)}</p>
				<p class="mt-1 font-mono text-xs text-slate-400">{t.href}</p>
			</li>
		{/each}
	</ul>
</section>
