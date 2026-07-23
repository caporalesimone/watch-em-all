<script lang="ts">
	// User notifier channels (7.F3): the Profile "Notification channels" section. Lists the
	// channels the admin has made available, each with its composite state, the personal
	// config form (dynamic, from the plugin schema), an on/off toggle and a Test button.
	// In-app is shown as always-on with no form. Self-contained/props-driven (FE-18).
	import { onMount } from 'svelte';
	import { _ } from 'svelte-i18n';

	import {
		ApiErr,
		listNotifiers,
		setNotifierConfig,
		setNotifierEnabled,
		testNotifier,
		type NotifierChannel
	} from '$lib/api/client';
	import DynamicConfigForm from '$lib/components/DynamicConfigForm.svelte';
	import { pushToast } from '$lib/stores/toasts';

	let channels = $state<NotifierChannel[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let busy = $state<string | null>(null); // plugin_id currently saving/toggling

	async function load(): Promise<void> {
		loading = true;
		error = null;
		try {
			channels = await listNotifiers();
		} catch {
			error = $_('notifiers.loadError');
		} finally {
			loading = false;
		}
	}

	onMount(load);

	function replace(updated: NotifierChannel): void {
		channels = channels.map((c) => (c.plugin_id === updated.plugin_id ? updated : c));
	}

	async function save(id: string, values: Record<string, unknown>): Promise<void> {
		busy = id;
		try {
			replace(await setNotifierConfig(id, values));
			pushToast($_('notifiers.saved'), 'success');
		} catch {
			pushToast($_('notifiers.saveError'), 'error');
		} finally {
			busy = null;
		}
	}

	async function toggle(c: NotifierChannel): Promise<void> {
		busy = c.plugin_id;
		try {
			replace(await setNotifierEnabled(c.plugin_id, !c.enabled));
		} catch {
			pushToast($_('notifiers.saveError'), 'error');
		} finally {
			busy = null;
		}
	}

	async function test(id: string): Promise<void> {
		busy = id;
		try {
			const res = await testNotifier(id);
			if (res.ok) pushToast($_('notifiers.testOk'), 'success');
			else pushToast($_('notifiers.testFail', { values: { error: res.error ?? '' } }), 'error');
		} catch (err) {
			const msg = err instanceof ApiErr ? err.detail : '';
			pushToast($_('notifiers.testFail', { values: { error: msg } }), 'error');
		} finally {
			busy = null;
		}
	}

	function statusKey(c: NotifierChannel): string {
		if (c.is_in_app) return 'notifiers.statusAlwaysOn';
		if (!c.available) return 'notifiers.statusUnavailable';
		if (!c.user_config_complete) return 'notifiers.statusNeedsSetup';
		return c.enabled ? 'notifiers.statusActive' : 'notifiers.statusOff';
	}

	function statusClass(c: NotifierChannel): string {
		if (c.active)
			return 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300';
		if (c.is_in_app)
			return 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300';
		return 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400';
	}
</script>

<section class="space-y-4 text-sm">
	<div>
		<h2 class="font-medium">{$_('notifiers.title')}</h2>
		<p class="mt-1 text-slate-500 dark:text-slate-400">{$_('notifiers.subtitle')}</p>
	</div>

	{#if loading}
		<p class="text-slate-500">{$_('common.loading')}</p>
	{:else if error}
		<p class="text-red-500">{error}</p>
	{:else}
		<div class="space-y-4">
			{#each channels as c (c.plugin_id)}
				<div class="rounded-lg border border-slate-200 p-4 dark:border-slate-800">
					<div class="flex items-center justify-between gap-2">
						<span class="font-medium">{c.display_name}</span>
						<span class="rounded px-1.5 py-0.5 text-xs {statusClass(c)}">{$_(statusKey(c))}</span>
					</div>

					{#if c.is_in_app}
						<p class="mt-2 text-slate-500 dark:text-slate-400">{$_('notifiers.inAppNote')}</p>
					{:else if !c.available}
						<p class="mt-2 text-slate-500 dark:text-slate-400">{$_('notifiers.unavailableNote')}</p>
					{:else}
						<div class="mt-3">
							<DynamicConfigForm
								schema={c.user_schema}
								config={c.config}
								isSet={c.is_set}
								busy={busy === c.plugin_id}
								onSubmit={(v) => save(c.plugin_id, v)}
							/>
						</div>
						<div class="mt-3 flex items-center gap-2 border-t border-slate-100 pt-3 dark:border-slate-800/60">
							<button
								type="button"
								disabled={busy === c.plugin_id || !c.user_config_complete}
								onclick={() => toggle(c)}
								class="rounded border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100 disabled:opacity-50 dark:border-slate-700 dark:hover:bg-slate-800"
							>
								{c.enabled ? $_('notifiers.deactivate') : $_('notifiers.activate')}
							</button>
							<button
								type="button"
								disabled={busy === c.plugin_id || !c.user_config_complete}
								onclick={() => test(c.plugin_id)}
								class="rounded border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100 disabled:opacity-50 dark:border-slate-700 dark:hover:bg-slate-800"
							>
								{$_('notifiers.test')}
							</button>
						</div>
					{/if}
				</div>
			{/each}
		</div>
	{/if}
</section>
