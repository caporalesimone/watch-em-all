<script lang="ts">
	// Admin feature-flags page (4.F6): auto-generated from GET /api/admin/feature-flags.
	// One card per flag key, one input per param, the widget inferred from the value's
	// type — so a new flag in KNOWN_FLAGS shows up here with no frontend change. Save
	// PATCHes the whole map. Flags are dev-only and non-persistent (reset at web restart).
	import { onMount } from 'svelte';
	import { _ } from 'svelte-i18n';

	import { getFeatureFlags, patchFeatureFlags, type FeatureFlags } from '$lib/api/client';
	import PageTitle from '$lib/components/PageTitle.svelte';
	import { changed, snapshot } from '$lib/forms';

	let flags = $state<FeatureFlags>({});
	let baseline = $state<FeatureFlags>({}); // what Save compares against (10.F23)
	let loading = $state(true);
	let saving = $state(false);
	let saved = $state(false);
	let error = $state<string | null>(null);

	const dirty = $derived(changed(flags, baseline));

	onMount(async () => {
		try {
			flags = await getFeatureFlags();
			baseline = snapshot(flags);
		} catch {
			error = $_('admin.featureFlags.loadError');
		} finally {
			loading = false;
		}
	});

	type Kind = 'boolean' | 'number' | 'string';
	function kindOf(value: unknown): Kind {
		if (typeof value === 'boolean') return 'boolean';
		if (typeof value === 'number') return 'number';
		return 'string';
	}

	function setParam(flag: string, param: string, value: unknown): void {
		flags = { ...flags, [flag]: { ...flags[flag], [param]: value } };
		saved = false;
	}

	async function save(): Promise<void> {
		saving = true;
		saved = false;
		error = null;
		try {
			flags = await patchFeatureFlags(flags);
			baseline = snapshot(flags);
			saved = true;
		} catch {
			error = $_('admin.featureFlags.saveError');
		} finally {
			saving = false;
		}
	}

	const inputClass =
		'rounded border border-slate-300 bg-white px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-900';
</script>

<section class="max-w-2xl space-y-6">
	<PageTitle title={$_('admin.featureFlags.title')} />
	<p class="text-sm text-slate-500">{$_('admin.featureFlags.hint')}</p>

	{#if loading}
		<p class="text-sm text-slate-500">{$_('common.loading')}</p>
	{:else if error}
		<p class="text-sm text-red-500">{error}</p>
	{:else if Object.keys(flags).length === 0}
		<p class="text-sm text-slate-500">{$_('admin.featureFlags.empty')}</p>
	{:else}
		<div class="space-y-4">
			{#each Object.entries(flags) as [flag, params] (flag)}
				<div class="rounded-lg border border-slate-200 p-4 dark:border-slate-800">
					<h2 class="mb-3 font-mono text-sm font-semibold">{flag}</h2>
					<div class="space-y-2">
						{#each Object.entries(params) as [param, value] (param)}
							<label class="flex items-center justify-between gap-4 text-sm">
								<span class="font-mono text-slate-500">{param}</span>
								{#if kindOf(value) === 'boolean'}
									<input
										type="checkbox"
										checked={Boolean(value)}
										onchange={(e) => setParam(flag, param, e.currentTarget.checked)}
									/>
								{:else if kindOf(value) === 'number'}
									<input
										class="{inputClass} w-40 text-right"
										type="number"
										value={Number(value)}
										oninput={(e) =>
											setParam(
												flag,
												param,
												Number.isNaN(e.currentTarget.valueAsNumber)
													? 0
													: e.currentTarget.valueAsNumber
											)}
									/>
								{:else}
									<input
										class="{inputClass} w-40"
										type="text"
										value={String(value)}
										oninput={(e) => setParam(flag, param, e.currentTarget.value)}
									/>
								{/if}
							</label>
						{/each}
					</div>
				</div>
			{/each}
		</div>

		<div class="flex items-center gap-3">
			<button
				class="rounded bg-slate-800 px-4 py-1.5 text-sm text-white hover:bg-slate-700 disabled:opacity-50 dark:bg-slate-200 dark:text-slate-900 dark:hover:bg-white"
				onclick={save}
				disabled={saving || !dirty}
			>
				{$_('common.save')}
			</button>
			{#if saved}<span class="text-sm text-green-600 dark:text-green-400">{$_('common.saved')}</span
				>{/if}
		</div>
	{/if}
</section>
