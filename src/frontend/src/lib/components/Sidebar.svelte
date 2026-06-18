<script lang="ts">
	import { page } from '$app/stores';
	import { _ } from 'svelte-i18n';

	import { signOut } from '$lib/stores/auth';
	import { mountedPlugins } from '$lib/stores/plugins';
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

		<!-- SCRAPERS group, last so it can grow without moving the core links (FDISC-R5). -->
		{#if $mountedPlugins.length > 0}
			<details open class="mt-4">
				<summary
					class="cursor-pointer px-3 py-1 text-xs font-semibold tracking-wide text-slate-400 uppercase select-none"
				>
					{$_('nav.scrapers')}
				</summary>
				<div class="mt-1 flex flex-col gap-1">
					{#each $mountedPlugins as plugin (plugin.name)}
						<a
							href={plugin.route_base}
							class={itemClass(plugin.route_base)}
							title={plugin.display_name}
						>
							{#if plugin.icon}
								<img src={plugin.icon} alt="" class="mr-2 inline h-4 w-4 align-text-bottom" />
							{/if}{plugin.display_name}
						</a>
					{/each}
				</div>
			</details>
		{/if}
	</nav>
	<button
		class="mt-4 rounded px-3 py-2 text-left text-sm text-slate-600 hover:bg-slate-200 dark:text-slate-300 dark:hover:bg-slate-800"
		onclick={() => signOut()}
	>
		{$_('nav.logout')}
	</button>
	{#if $version}
		<!-- Same text, now a link to Swagger (new tab), centered in the sidebar. -->
		<a
			href="/api/docs"
			target="_blank"
			rel="noopener"
			class="mt-1 block px-3 text-center text-[11px] break-all text-slate-400 dark:text-slate-600"
			title={$version}
		>
			v{$version}
		</a>
	{/if}
</aside>
