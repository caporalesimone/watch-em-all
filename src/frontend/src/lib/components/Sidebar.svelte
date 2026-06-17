<script lang="ts">
	import { page } from '$app/stores';
	import { _ } from 'svelte-i18n';

	import { signOut } from '$lib/stores/auth';
	import { version } from '$lib/stores/version';

	const links = [
		{ href: '/', key: 'nav.dashboard' },
		{ href: '/profile', key: 'nav.profile' }
	];

	function itemClass(href: string): string {
		const base = 'rounded px-3 py-2 text-sm hover:bg-slate-200 dark:hover:bg-slate-800';
		const active = $page.url.pathname === href ? ' bg-slate-200 dark:bg-slate-800' : '';
		return base + active;
	}
</script>

<aside
	class="flex w-56 flex-col border-r border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-900"
>
	<div class="mb-6 text-lg font-semibold">{$_('app.name')}</div>
	<nav class="flex flex-1 flex-col gap-1">
		{#each links as link (link.href)}
			<a href={link.href} class={itemClass(link.href)}>{$_(link.key)}</a>
		{/each}
	</nav>
	<button
		class="mt-4 rounded px-3 py-2 text-left text-sm text-slate-600 hover:bg-slate-200 dark:text-slate-300 dark:hover:bg-slate-800"
		onclick={() => signOut()}
	>
		{$_('nav.logout')}
	</button>
	{#if $version}
		<p class="mt-1 px-3 text-[11px] break-all text-slate-400 dark:text-slate-600" title={$version}>
			v{$version}
		</p>
	{/if}
</aside>
