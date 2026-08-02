<script lang="ts">
	// User notifier channels (7.F3): the Profile "Notification channels" section. Lists the
	// channels the admin has made available, each with its composite state, the personal
	// config form (dynamic, from the plugin schema) and an on/off toggle.
	// In-app is shown as always-on with no form. Self-contained/props-driven (FE-18).
	//
	// The Test button is gone since 10.X4. It was here from when a user typed their own
	// delivery address into this page; since 10.B23 the address *is* the account, and it has
	// already proved it works — the password that got this person in arrived on it. What the
	// button really probed was the server's SMTP config, which is the administrator's to fix
	// and is tested from their own page.
	import { onMount } from 'svelte';
	import { _ } from 'svelte-i18n';

	import {
		listNotifiers,
		setNotifierConfig,
		setNotifierEnabled,
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
						<!-- A channel with nothing to fill in shows no form at all. Since 10.B25 email
						     is exactly that: the address comes from the account, so what is left is
						     the switch — and an empty form with a Save button under it would invite a
						     click that does nothing. -->
						{#if c.user_schema.length > 0}
							<div class="mt-3">
								<DynamicConfigForm
									schema={c.user_schema}
									config={c.config}
									isSet={c.is_set}
									busy={busy === c.plugin_id}
									onSubmit={(v) => save(c.plugin_id, v)}
								/>
							</div>
						{/if}
						<div
							class="mt-3 flex items-center gap-2 border-t border-slate-100 pt-3 dark:border-slate-800/60"
						>
							<button
								type="button"
								disabled={busy === c.plugin_id || !c.user_config_complete}
								onclick={() => toggle(c)}
								class="rounded border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100 disabled:opacity-50 dark:border-slate-700 dark:hover:bg-slate-800"
							>
								{c.enabled ? $_('notifiers.deactivate') : $_('notifiers.activate')}
							</button>
						</div>
					{/if}
				</div>
			{/each}
		</div>
	{/if}
</section>
