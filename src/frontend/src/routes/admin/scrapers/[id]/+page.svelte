<script lang="ts">
	// Per-scraper config subpage (4.F2): the core reserved parameters (politeness, HTTP
	// timeout, cache half-life, manual scrape-now interval) the system applies on every run.
	// The slot editor (4.F1) and the plugin's own declared fields (phase 7+) join this page later.
	import { page } from '$app/stores';
	import { _ } from 'svelte-i18n';

	import {
		clearScraperCache,
		getScraperConfig,
		listScrapers,
		patchScraperConfig,
		type ScraperConfig
	} from '$lib/api/client';
	import PageTitle from '$lib/components/PageTitle.svelte';

	let config = $state<ScraperConfig | null>(null);
	let displayName = $state('');
	let loading = $state(true);
	let saving = $state(false);
	let saved = $state(false);
	let error = $state<string | null>(null);

	let clearing = $state(false);
	let clearConfirm = $state(false);
	let clearedMsg = $state<string | null>(null);

	// Reload when the route param changes (the component is reused across scrapers).
	$effect(() => {
		const sid = $page.params.id;
		if (sid) void load(sid);
	});

	async function load(sid: string): Promise<void> {
		loading = true;
		error = null;
		saved = false;
		try {
			const [cfg, list] = await Promise.all([getScraperConfig(sid), listScrapers()]);
			config = cfg;
			displayName = list.find((s) => s.scraper_id === sid)?.display_name ?? sid;
		} catch {
			error = $_('admin.scrapers.loadError');
		} finally {
			loading = false;
		}
	}

	function setField(key: keyof ScraperConfig, value: number): void {
		if (config) config = { ...config, [key]: value };
		saved = false;
	}

	async function save(): Promise<void> {
		const sid = $page.params.id;
		if (!config || !sid) return;
		saving = true;
		saved = false;
		error = null;
		try {
			config = await patchScraperConfig(sid, config);
			saved = true;
		} catch {
			error = $_('admin.scrapers.saveError');
		} finally {
			saving = false;
		}
	}

	async function clearCache(): Promise<void> {
		const sid = $page.params.id;
		if (!sid) return;
		clearing = true;
		clearedMsg = null;
		error = null;
		try {
			const { deleted } = await clearScraperCache(sid);
			clearedMsg = $_('admin.scrapers.cacheCleared', { values: { n: deleted } });
		} catch {
			error = $_('admin.scrapers.clearError');
		} finally {
			clearing = false;
			clearConfirm = false;
		}
	}

	const fields: { key: keyof ScraperConfig; step: number }[] = [
		// Steps sized for the shipped defaults (11000 ms, 720 min): a 50 ms step meant
		// hundreds of clicks to move the politeness delay by anything meaningful.
		{ key: 'politeness_delay_ms', step: 500 },
		{ key: 'http_timeout_s', step: 1 },
		{ key: 'cache_ttl_min', step: 30 },
		{ key: 'scrape_now_min_interval_s', step: 1 }
	];

	const inputClass =
		'rounded border border-slate-300 bg-white px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-900';
</script>

<section class="max-w-2xl space-y-6">
	<a href="/admin/scrapers" class="text-sm text-sky-600 hover:underline dark:text-sky-400">
		{$_('admin.scrapers.back')}
	</a>

	{#if loading}
		<p class="text-sm text-slate-500">{$_('common.loading')}</p>
	{:else if error && !config}
		<p class="text-sm text-red-500">{error}</p>
	{:else if config}
		<PageTitle title={$_('admin.scrapers.configTitle', { values: { name: displayName } })} />

		<div class="rounded-lg border border-slate-200 p-4 dark:border-slate-800">
			<h2 class="font-semibold">{$_('admin.scrapers.reserved')}</h2>
			<p class="mt-1 mb-3 text-sm text-slate-500">{$_('admin.scrapers.reservedHint')}</p>
			<div class="space-y-2">
				{#each fields as f (f.key)}
					<label class="flex items-center justify-between gap-4 text-sm">
						<span class="flex flex-col pr-4">
							<span class="text-slate-600 dark:text-slate-300"
								>{$_(`admin.scrapers.fields.${f.key}`)}</span
							>
							<span class="text-xs text-slate-400">{$_(`admin.scrapers.fieldHints.${f.key}`)}</span>
						</span>
						<input
							class="{inputClass} w-40 text-right"
							type="number"
							step={f.step}
							min="0"
							value={config[f.key]}
							oninput={(e) =>
								setField(
									f.key,
									Number.isNaN(e.currentTarget.valueAsNumber) ? 0 : e.currentTarget.valueAsNumber
								)}
						/>
					</label>
				{/each}
			</div>
		</div>

		<div class="flex items-center gap-3">
			<button
				class="rounded bg-slate-800 px-4 py-1.5 text-sm text-white hover:bg-slate-700 disabled:opacity-50 dark:bg-slate-200 dark:text-slate-900 dark:hover:bg-white"
				onclick={save}
				disabled={saving}
			>
				{$_('common.save')}
			</button>
			{#if saved}<span class="text-sm text-green-600 dark:text-green-400">{$_('common.saved')}</span
				>{/if}
			{#if error}<span class="text-sm text-red-500">{error}</span>{/if}
		</div>

		<div class="rounded-lg border border-slate-200 p-4 dark:border-slate-800">
			<h2 class="font-semibold">{$_('admin.scrapers.cache')}</h2>
			<p class="mt-1 mb-3 text-sm text-slate-500">{$_('admin.scrapers.cacheHint')}</p>
			{#if clearConfirm}
				<div class="flex flex-wrap items-center gap-3">
					<span class="text-sm">{$_('admin.scrapers.clearConfirm')}</span>
					<button
						class="rounded bg-red-700 px-3 py-1.5 text-sm text-white hover:bg-red-600 disabled:opacity-50"
						onclick={clearCache}
						disabled={clearing}
					>
						{$_('admin.scrapers.clearCache')}
					</button>
					<button
						class="rounded border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100 disabled:opacity-50 dark:border-slate-700 dark:hover:bg-slate-800"
						onclick={() => (clearConfirm = false)}
						disabled={clearing}
					>
						{$_('common.cancel')}
					</button>
				</div>
			{:else}
				<div class="flex items-center gap-3">
					<button
						class="rounded border border-red-300 px-3 py-1.5 text-sm text-red-700 hover:bg-red-50 dark:border-red-800 dark:text-red-400 dark:hover:bg-red-950"
						onclick={() => {
							clearConfirm = true;
							clearedMsg = null;
						}}
					>
						{$_('admin.scrapers.clearCache')}
					</button>
					{#if clearedMsg}<span class="text-sm text-green-600 dark:text-green-400"
							>{clearedMsg}</span
						>{/if}
				</div>
			{/if}
		</div>
	{/if}
</section>
