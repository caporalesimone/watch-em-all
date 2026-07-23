<script lang="ts">
	// Admin notifiers (7.F4): per channel, the system config form (dynamic, from the plugin
	// schema; secrets write-only), the global kill-switch (PCFG-R8, applies to in-app too), and
	// a channel test with an admin-supplied target. In-app has no system config — only the switch.
	import { onMount } from 'svelte';
	import { _ } from 'svelte-i18n';

	import {
		ApiErr,
		listAdminNotifiers,
		setAdminNotifierConfig,
		setAdminNotifierEnabled,
		testAdminNotifier,
		type AdminNotifier
	} from '$lib/api/client';
	import DynamicConfigForm from '$lib/components/DynamicConfigForm.svelte';
	import PageTitle from '$lib/components/PageTitle.svelte';
	import { pushToast } from '$lib/stores/toasts';

	let channels = $state<AdminNotifier[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let busy = $state<string | null>(null);

	async function load(): Promise<void> {
		loading = true;
		error = null;
		try {
			channels = await listAdminNotifiers();
		} catch {
			error = $_('admin.notifiers.loadError');
		} finally {
			loading = false;
		}
	}

	onMount(load);

	function replace(updated: AdminNotifier): void {
		channels = channels.map((c) => (c.plugin_id === updated.plugin_id ? updated : c));
	}

	async function saveConfig(id: string, values: Record<string, unknown>): Promise<void> {
		busy = id;
		try {
			replace(await setAdminNotifierConfig(id, values));
			pushToast($_('admin.notifiers.saved'), 'success');
		} catch {
			pushToast($_('admin.notifiers.saveError'), 'error');
		} finally {
			busy = null;
		}
	}

	async function toggle(c: AdminNotifier): Promise<void> {
		busy = c.plugin_id;
		try {
			replace(await setAdminNotifierEnabled(c.plugin_id, !c.enabled));
		} catch {
			pushToast($_('admin.notifiers.saveError'), 'error');
		} finally {
			busy = null;
		}
	}

	async function test(id: string, values: Record<string, unknown>): Promise<void> {
		busy = id;
		try {
			const res = await testAdminNotifier(id, values);
			if (res.ok) pushToast($_('admin.notifiers.testOk'), 'success');
			else
				pushToast(
					$_('admin.notifiers.testFail', { values: { error: res.error ?? '' } }),
					'error'
				);
		} catch (err) {
			const msg = err instanceof ApiErr ? err.detail : '';
			pushToast($_('admin.notifiers.testFail', { values: { error: msg } }), 'error');
		} finally {
			busy = null;
		}
	}
</script>

<section class="max-w-2xl space-y-6">
	<PageTitle title={$_('admin.notifiers.title')} />
	<p class="text-sm text-slate-500 dark:text-slate-400">{$_('admin.notifiers.subtitle')}</p>

	{#if loading}
		<p class="text-sm text-slate-500">{$_('common.loading')}</p>
	{:else if error}
		<p class="text-sm text-red-500">{error}</p>
	{:else if channels.length === 0}
		<p class="text-sm text-slate-500">{$_('admin.notifiers.empty')}</p>
	{:else}
		<div class="space-y-4">
			{#each channels as c (c.plugin_id)}
				<div class="space-y-3 rounded-lg border border-slate-200 p-4 text-sm dark:border-slate-800">
					<div class="flex items-center justify-between gap-2">
						<div class="flex items-center gap-2">
							<span class="font-medium">{c.display_name}</span>
							{#if !c.is_in_app}
								<span
									class="rounded px-1.5 py-0.5 text-xs {c.admin_config_complete
										? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300'
										: 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400'}"
								>
									{c.admin_config_complete
										? $_('admin.notifiers.available')
										: $_('admin.notifiers.notConfigured')}
								</span>
							{/if}
						</div>
						<button
							type="button"
							disabled={busy === c.plugin_id}
							onclick={() => toggle(c)}
							class="rounded border px-3 py-1.5 text-sm disabled:opacity-50 {c.enabled
								? 'border-slate-300 hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800'
								: 'border-amber-400 bg-amber-50 text-amber-800 dark:border-amber-700 dark:bg-amber-900/30 dark:text-amber-300'}"
						>
							{c.enabled ? $_('admin.notifiers.disable') : $_('admin.notifiers.enable')}
						</button>
					</div>

					{#if c.is_in_app}
						<p class="text-slate-500 dark:text-slate-400">{$_('admin.notifiers.inAppNote')}</p>
					{:else}
						<div>
							<h3 class="mb-2 text-xs font-semibold text-slate-400 uppercase">
								{$_('admin.notifiers.configTitle')}
							</h3>
							<DynamicConfigForm
								schema={c.admin_schema}
								config={c.config}
								isSet={c.is_set}
								busy={busy === c.plugin_id}
								onSubmit={(v) => saveConfig(c.plugin_id, v)}
							/>
						</div>
						{#if c.user_schema.length > 0}
							<div class="border-t border-slate-100 pt-3 dark:border-slate-800/60">
								<h3 class="mb-1 text-xs font-semibold text-slate-400 uppercase">
									{$_('admin.notifiers.testTitle')}
								</h3>
								<p class="mb-2 text-xs text-slate-400">{$_('admin.notifiers.testHint')}</p>
								<DynamicConfigForm
									schema={c.user_schema}
									busy={busy === c.plugin_id}
									submitLabel={$_('admin.notifiers.test')}
									onSubmit={(v) => test(c.plugin_id, v)}
								/>
							</div>
						{/if}
					{/if}
				</div>
			{/each}
		</div>
	{/if}
</section>
