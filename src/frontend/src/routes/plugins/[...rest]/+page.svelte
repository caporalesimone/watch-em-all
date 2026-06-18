<script lang="ts">
	import type { Component } from 'svelte';
	import { page } from '$app/stores';
	import { _ } from 'svelte-i18n';

	import { mountedPlugins, pluginsReady, type MountedPlugin } from '$lib/stores/plugins';

	// The plugin's frontend entry exports `default { component }` (FDISC-R3).
	interface PluginEntry {
		default: { component: Component };
	}

	// Resolve the plugin whose route_base owns the current path (the plugin manages
	// its own sub-views under it). Reactive to both the path and discovery state.
	const current = $derived(
		$mountedPlugins.find(
			(plugin) =>
				$page.url.pathname === plugin.route_base ||
				$page.url.pathname.startsWith(plugin.route_base + '/')
		)
	);

	async function load(plugin: MountedPlugin): Promise<Component> {
		if (plugin.i18n) await plugin.i18n(); // register the plugin's i18n namespace
		const module = (await plugin.component()) as PluginEntry;
		return module.default.component;
	}
</script>

{#if !$pluginsReady}
	<p class="text-sm text-slate-500">{$_('common.loading')}</p>
{:else if current}
	{#await load(current)}
		<p class="text-sm text-slate-500">{$_('common.loading')}</p>
	{:then Plugin}
		<Plugin />
	{:catch}
		<p class="text-sm text-slate-500">{$_('plugins.notFound')}</p>
	{/await}
{:else}
	<p class="text-sm text-slate-500">{$_('plugins.notFound')}</p>
{/if}
