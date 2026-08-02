<script lang="ts">
	// Admin system settings (4.F7, MNT-R3): runtime, DB-first — edited without a restart. The
	// worker re-reads the values on each run/purge. Feature flags live on a separate child page.
	import { onMount } from 'svelte';
	import { _ } from 'svelte-i18n';

	import { getSettings, patchSettings, type SystemSettings } from '$lib/api/client';
	import PageTitle from '$lib/components/PageTitle.svelte';
	import { changed, snapshot } from '$lib/forms';

	let settings = $state<SystemSettings | null>(null);
	// What Save compares against (10.F23): the values as the server last handed them over.
	let baseline = $state<SystemSettings | null>(null);
	let loading = $state(true);
	let saving = $state(false);
	let saved = $state(false);
	let error = $state<string | null>(null);

	const dirty = $derived(settings !== null && changed(settings, baseline));

	onMount(async () => {
		try {
			settings = await getSettings();
			baseline = snapshot(settings);
		} catch {
			error = $_('admin.settings.loadError');
		} finally {
			loading = false;
		}
	});

	function setExpiry(value: number): void {
		if (!settings) return;
		settings = {
			...settings,
			password_expiry_days: value as SystemSettings['password_expiry_days']
		};
		saved = false;
	}

	function setField(key: keyof SystemSettings, value: number): void {
		if (settings) settings = { ...settings, [key]: value };
		saved = false;
	}

	async function save(): Promise<void> {
		if (!settings) return;
		saving = true;
		saved = false;
		error = null;
		try {
			settings = await patchSettings(settings);
			baseline = snapshot(settings);
			saved = true;
		} catch {
			error = $_('admin.settings.saveError');
		} finally {
			saving = false;
		}
	}

	const fields: { key: keyof SystemSettings; min: number; max?: number }[] = [
		{ key: 'scraper_run_timeout_min', min: 1 },
		{ key: 'log_retention_days', min: 0 },
		{ key: 'catchup_warning_min', min: 0 },
		{ key: 'user_deletion_retention_days', min: 1 },
		// Both belong to the nightly window (10.B8a/b). The hour is capped at 23 rather than
		// left open: a "24" would silently mean a window that never opens.
		{ key: 'maintenance_hour', min: 0, max: 23 },
		{ key: 'alert_keep_last', min: 0 }
	];

	// Fixed options rather than a number box (10.F14): the backend only accepts these five,
	// and a free field would let an admin type 3 and put everybody on a forced change. The
	// labels are written out, not built from the value, so the i18n gate can see them.
	const expiryOptions = $derived([
		{ value: 0 as const, label: $_('admin.settings.expiryNever') },
		{ value: 30 as const, label: $_('admin.settings.expiry30') },
		{ value: 90 as const, label: $_('admin.settings.expiry90') },
		{ value: 180 as const, label: $_('admin.settings.expiry180') },
		{ value: 365 as const, label: $_('admin.settings.expiry365') }
	]);

	const inputClass =
		'rounded border border-slate-300 bg-white px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-900';
</script>

<section class="max-w-2xl space-y-6">
	<PageTitle title={$_('admin.settings.title')} />
	<p class="text-sm text-slate-500">{$_('admin.settings.hint')}</p>

	{#if loading}
		<p class="text-sm text-slate-500">{$_('common.loading')}</p>
	{:else if error && !settings}
		<p class="text-sm text-red-500">{error}</p>
	{:else if settings}
		<div class="rounded-lg border border-slate-200 p-4 dark:border-slate-800">
			<div class="space-y-3">
				{#each fields as f (f.key)}
					<label class="flex items-center justify-between gap-4 text-sm">
						<span class="flex flex-col pr-4">
							<span class="text-slate-600 dark:text-slate-300"
								>{$_(`admin.settings.fields.${f.key}`)}</span
							>
							<span class="text-xs text-slate-400">{$_(`admin.settings.fieldHints.${f.key}`)}</span>
						</span>
						<input
							class="{inputClass} w-40 text-right"
							type="number"
							min={f.min}
							step="1"
							value={settings[f.key]}
							oninput={(e) =>
								setField(
									f.key,
									Number.isNaN(e.currentTarget.valueAsNumber)
										? f.min
										: e.currentTarget.valueAsNumber
								)}
						/>
					</label>
				{/each}

				<label class="flex items-center justify-between gap-4 text-sm">
					<span class="flex flex-col pr-4">
						<span class="text-slate-600 dark:text-slate-300"
							>{$_('admin.settings.passwordExpiry')}</span
						>
						<span class="text-xs text-slate-400">{$_('admin.settings.passwordExpiryHint')}</span>
					</span>
					<select
						class="{inputClass} w-40"
						value={settings.password_expiry_days}
						onchange={(e) => setExpiry(Number(e.currentTarget.value))}
					>
						{#each expiryOptions as option (option.value)}
							<option value={option.value}>{option.label}</option>
						{/each}
					</select>
				</label>
			</div>
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
			{#if error}<span class="text-sm text-red-500">{error}</span>{/if}
		</div>
	{/if}
</section>
