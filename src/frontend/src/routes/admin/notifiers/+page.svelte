<script lang="ts">
	// Admin notifiers (7.F4, restructured by 10.B28/10.F27): per channel, the system config form
	// (dynamic, from the plugin schema; secrets write-only), a validation step, and the global
	// kill-switch (PCFG-R8, applies to in-app too).
	//
	// The page is one loop, not three independent buttons, and it is laid out in that order:
	//
	//   1. fill in the settings and save them;
	//   2. **Validate** — a real message goes out to the admin's own account, and if the server
	//      takes it the settings are recorded as proven;
	//   3. only then does the switch come alive.
	//
	// Editing a validated setting switches the channel off again (the server does it), because the
	// proof was about the old value. That is why saving here can visibly turn a channel off — it
	// is not a side effect, it is the rule.
	import { onMount } from 'svelte';
	import { _ } from 'svelte-i18n';

	import {
		ApiErr,
		listAdminNotifiers,
		setAdminNotifierConfig,
		setAdminNotifierEnabled,
		validateAdminNotifier,
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
			const updated = await setAdminNotifierConfig(id, values);
			replace(updated);
			// Said out loud, because the row visibly changes underneath: new settings are settings
			// nothing has proven, so the channel goes back to off and has to be validated again.
			pushToast(
				updated.requires_validation && !updated.validated
					? $_('admin.notifiers.savedNeedsValidation')
					: $_('admin.notifiers.saved'),
				'success'
			);
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
		} catch (err) {
			// The one refusal this button can meet: switching on something unproven. The control is
			// disabled for that case, so this only fires on a stale page — say why anyway.
			const stale = err instanceof ApiErr && err.code === 'not_validated';
			pushToast(
				stale ? $_('admin.notifiers.mustValidate') : $_('admin.notifiers.saveError'),
				'error'
			);
			if (stale) await load();
		} finally {
			busy = null;
		}
	}

	async function validate(c: AdminNotifier): Promise<void> {
		busy = c.plugin_id;
		try {
			const res = await validateAdminNotifier(c.plugin_id);
			replace(res.channel);
			if (res.ok) pushToast($_('admin.notifiers.validateOk'), 'success');
			else
				pushToast(
					$_('admin.notifiers.validateFail', { values: { error: res.error ?? '' } }),
					'error'
				);
		} catch (err) {
			const incomplete = err instanceof ApiErr && err.code === 'config_incomplete';
			const msg = err instanceof ApiErr ? err.detail : '';
			pushToast(
				incomplete
					? $_('admin.notifiers.validateIncomplete')
					: $_('admin.notifiers.validateFail', { values: { error: msg } }),
				'error'
			);
		} finally {
			busy = null;
		}
	}

	// Two badges, because they answer two different questions and one cannot stand for the other:
	// *are the settings proven* and *is anything going out through this*. A channel can be proven
	// and switched off, which is a perfectly ordinary state and used to be unsayable.
	function stateKey(c: AdminNotifier): string {
		if (!c.admin_config_complete) return 'admin.notifiers.notConfigured';
		return c.enabled ? 'admin.notifiers.statusActive' : 'admin.notifiers.statusOff';
	}

	function stateClass(c: AdminNotifier): string {
		if (!c.admin_config_complete)
			return 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400';
		return c.enabled
			? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300'
			: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300';
	}

	function when(iso: string | null): string {
		return iso ? new Date(iso).toLocaleString() : '';
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
					<div class="flex flex-wrap items-center justify-between gap-2">
						<div class="flex flex-wrap items-center gap-2">
							<span class="font-medium">{c.display_name}</span>
							{#if !c.is_in_app}
								<span class="rounded px-1.5 py-0.5 text-xs {stateClass(c)}">{$_(stateKey(c))}</span>
								{#if c.validated}
									<span
										class="rounded px-1.5 py-0.5 text-xs bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300"
										title={when(c.validated_at)}
									>
										{$_('admin.notifiers.validated')}
									</span>
								{:else}
									<span
										class="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-500 dark:bg-slate-800 dark:text-slate-400"
									>
										{$_('admin.notifiers.notValidated')}
									</span>
								{/if}
							{/if}
						</div>
						<button
							type="button"
							disabled={busy === c.plugin_id || (!c.enabled && !c.validated)}
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

						<!-- Step two of the loop, so it sits between the form and nothing else. The
						     hint says what the word "validated" is worth, because the honest claim is
						     narrow: the server took the message. What it does with it afterwards is
						     between that server and the recipient. -->
						<div class="border-t border-slate-100 pt-3 dark:border-slate-800/60">
							<h3 class="mb-1 text-xs font-semibold text-slate-400 uppercase">
								{$_('admin.notifiers.validateTitle')}
							</h3>
							<p class="mb-2 text-xs text-slate-400">{$_('admin.notifiers.validateHint')}</p>
							<div class="flex flex-wrap items-center gap-3">
								<button
									type="button"
									disabled={busy === c.plugin_id || !c.admin_config_complete}
									onclick={() => validate(c)}
									class="rounded border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100 disabled:opacity-50 dark:border-slate-700 dark:hover:bg-slate-800"
								>
									{c.validated
										? $_('admin.notifiers.validateAgain')
										: $_('admin.notifiers.validate')}
								</button>
								{#if c.validated}
									<span class="text-xs text-slate-400">
										{$_('admin.notifiers.validatedAt', {
											values: { date: when(c.validated_at) }
										})}
									</span>
								{:else if c.admin_config_complete}
									<span class="text-xs text-amber-700 dark:text-amber-400">
										{$_('admin.notifiers.mustValidate')}
									</span>
								{/if}
							</div>
						</div>
					{/if}
				</div>
			{/each}
		</div>
	{/if}
</section>
