<script lang="ts">
	import { page } from '$app/stores';
	import { _ } from 'svelte-i18n';

	import { auth, signOut } from '$lib/stores/auth';
	import { mountedPlugins } from '$lib/stores/plugins';
	import { version } from '$lib/stores/version';

	// Roles don't overlap (personas-and-roles.md): an admin governs (no personal
	// catalog/carts), a user owns their data. The shell shows one or the other.
	const isAdmin = $derived(($auth.user?.role ?? 'user') === 'admin');

	type NavItem = { href: string; key: string; children?: { href: string; key: string }[] };
	const primary = $derived<NavItem[]>(
		isAdmin
			? [
					{ href: '/admin/logs', key: 'nav.systemLogs' },
					{ href: '/admin/users', key: 'nav.users' },
					{
						href: '/admin/scrapers',
						key: 'nav.scrapers',
						children: [{ href: '/admin/scrapers/schedule', key: 'admin.scrapers.scheduleTitle' }]
					},
					{ href: '/admin/notifiers', key: 'nav.notifiers' },
					{
						href: '/admin/settings',
						key: 'nav.settings',
						children: [{ href: '/admin/feature-flags', key: 'nav.featureFlags' }]
					}
				]
			: [
					{ href: '/', key: 'nav.dashboard' },
					{ href: '/catalog', key: 'nav.catalog' }
				]
	);

	function itemClass(href: string): string {
		const base = 'rounded px-3 py-2 text-sm hover:bg-slate-200 dark:hover:bg-slate-800';
		const active = $page.url.pathname === href ? ' bg-slate-200 dark:bg-slate-800' : '';
		return base + active;
	}
</script>

<aside
	class="flex w-56 flex-col border-r border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-900"
>
	<div class="mb-6 text-center text-lg font-semibold">{$_('app.name')}</div>
	<nav class="flex flex-1 flex-col gap-1">
		{#each primary as link (link.href)}
			<a href={link.href} class={itemClass(link.href)}>{$_(link.key)}</a>
			{#if link.children}
				{#each link.children as child (child.href)}
					<!-- Child entry: clickable, indented (ml-4) to read as a sub-page. -->
					<a href={child.href} class="{itemClass(child.href)} ml-4 text-[13px]">{$_(child.key)}</a>
				{/each}
			{/if}
		{/each}
		<a href="/profile" class={itemClass('/profile')}>{$_('nav.profile')}</a>

		<!-- SCRAPERS group (users only), last so it can grow without moving the core links. -->
		{#if !isAdmin && $mountedPlugins.length > 0}
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
		<!-- Version centered between two thin rules (same color), linking to Swagger. -->
		<div
			class="mt-1 flex items-center gap-2 px-3 text-[11px] text-slate-400 dark:text-slate-600"
			title={$version}
		>
			<span class="h-px flex-1 bg-current"></span>
			<a href="/api/docs" target="_blank" rel="noopener" class="whitespace-nowrap">v{$version}</a>
			<span class="h-px flex-1 bg-current"></span>
		</div>
	{/if}
</aside>
