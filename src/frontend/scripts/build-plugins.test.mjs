import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import { collectPlugins, generate, renderRegistry } from './build-plugins.mjs';

function scaffold(root, folder, name, manifest) {
	const dir = join(root, folder, name);
	mkdirSync(dir, { recursive: true });
	writeFileSync(join(dir, 'manifest.json'), JSON.stringify(manifest), 'utf8');
}

const scraper = (name, enabled = true) => ({
	name,
	display_name: name,
	type: 'scraper',
	version: '1.0.0',
	api_version: 1,
	enabled,
	backend: { entry: 'backend/__init__.py' },
	frontend: {
		entry: 'frontend/index.ts',
		route_base: `/plugins/${name.replaceAll('_', '-')}`,
		i18n: 'frontend/i18n'
	}
});

const notifier = (name) => ({
	name,
	display_name: name,
	type: 'notifier',
	version: '1.0.0',
	api_version: 1,
	enabled: true,
	backend: { entry: 'backend/__init__.py' }
});

describe('build:plugins generator', () => {
	it('keeps enabled scrapers with a frontend, drops disabled and UI-less plugins', () => {
		const root = mkdtempSync(join(tmpdir(), 'wea-plugins-'));
		scaffold(root, 'scrapers', 'tp_scraper', scraper('tp_scraper'));
		scaffold(root, 'scrapers', 'off_one', scraper('off_one', false));
		scaffold(root, 'notifiers', 'tp_notifier', notifier('tp_notifier'));

		const entries = collectPlugins(root);
		expect(entries.map((e) => e.name)).toEqual(['tp_scraper']);
		expect(entries[0].route_base).toBe('/plugins/tp-scraper');
		expect(entries[0].component).toBe('$plugins/scrapers/tp_scraper/frontend/index');
		expect(entries[0].i18n).toBe('$plugins/scrapers/tp_scraper/frontend/i18n');
	});

	it('renders a typed module with lazy imports', () => {
		const out = renderRegistry([
			{
				name: 'tp_scraper',
				route_base: '/plugins/tp-scraper',
				component: '$plugins/scrapers/tp_scraper/frontend/index',
				i18n: '$plugins/scrapers/tp_scraper/frontend/i18n'
			}
		]);
		expect(out).toContain('export const plugins: GeneratedPlugin[] = [');
		expect(out).toContain('import("$plugins/scrapers/tp_scraper/frontend/index")');
		expect(out).toContain('route_base: "/plugins/tp-scraper"');
	});

	it('writes an empty registry when there are no plugins', () => {
		const emptyRoot = mkdtempSync(join(tmpdir(), 'wea-empty-'));
		const out = join(mkdtempSync(join(tmpdir(), 'wea-out-')), 'plugin-registry.ts');
		const entries = generate(emptyRoot, out);
		expect(entries).toEqual([]);
		const content = readFileSync(out, 'utf8');
		expect(content).toContain('export const plugins: GeneratedPlugin[] = [');
		expect(content).not.toContain('import(');
	});
});
