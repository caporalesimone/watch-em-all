// Plugin discovery state (FDISC-R2). At boot the SPA fetches the enabled+loaded
// plugins from the backend and reconciles them against the build-time generated
// registry: a scraper present in both gets a route + sidebar entry. Notifiers are
// never in the nav/routes (their UI lives elsewhere).
import { writable } from 'svelte/store';

import * as api from '$lib/api/client';

import { plugins as generated } from '../../generated/plugin-registry';

export interface MountedPlugin {
	name: string;
	display_name: string;
	route_base: string;
	icon: string | null;
	component: () => Promise<unknown>;
	i18n: (() => Promise<unknown>) | null;
}

/** Scrapers that are both enabled at runtime and present in this bundle. */
export const mountedPlugins = writable<MountedPlugin[]>([]);
/** False until the first discovery completes (so routes don't flash "not found"). */
export const pluginsReady = writable(false);

export async function loadPlugins(): Promise<void> {
	let discovered: api.PluginInfo[] = [];
	try {
		discovered = await api.getPlugins();
	} catch {
		discovered = [];
	}
	const generatedByName = new Map(generated.map((entry) => [entry.name, entry]));
	const discoveredScrapers = new Set<string>();
	const mounted: MountedPlugin[] = [];
	for (const plugin of discovered) {
		// Notifiers never appear in the sidebar or as routes.
		if (plugin.type !== 'scraper' || !plugin.route_base) continue;
		discoveredScrapers.add(plugin.name);
		const entry = generatedByName.get(plugin.name);
		if (!entry) {
			// Enabled in the backend but missing from this bundle: hide it (never a
			// broken page) and tell the developer the build is stale (FDISC-R4).
			console.warn(
				`Plugin "${plugin.name}" is enabled in the backend but missing from this ` +
					`frontend build — rebuild the frontend (npm run build) to mount it.`
			);
			continue;
		}
		mounted.push({
			name: plugin.name,
			display_name: plugin.display_name,
			route_base: plugin.route_base,
			icon: plugin.icon,
			component: entry.component,
			i18n: entry.i18n
		});
	}
	// The reverse mismatch: bundled but not loaded by the backend (FDISC-R4). Not an
	// error — it just won't appear; surface it so the skew is visible.
	for (const entry of generated) {
		if (!discoveredScrapers.has(entry.name)) {
			console.warn(
				`Plugin "${entry.name}" is bundled in the frontend but not loaded by the ` +
					`backend — rebuild/restart to reconcile.`
			);
		}
	}
	mountedPlugins.set(mounted);
	pluginsReady.set(true);
}

/** Clear discovery state on sign-out. */
export function resetPlugins(): void {
	mountedPlugins.set([]);
	pluginsReady.set(false);
}
