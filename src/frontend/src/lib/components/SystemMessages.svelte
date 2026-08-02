<script lang="ts">
	// The system-message catalog, editable (10.F11, ADMSG-R7/R8).
	//
	// One accordion row per key the core declares — not per row in the table, which is the whole
	// point of ADMSG-R9: a message added to the core appears here with nothing to seed. The badge
	// says whether what is in force is the default or a rewrite.
	//
	// The editor is the same Write / Preview pair as the announcement composer, rendered by the
	// same server endpoint, so an admin sees the message exactly as it will be delivered rather
	// than a second approximation of it (the reasoning of 10.F9).
	import { onMount } from 'svelte';
	import { _ } from 'svelte-i18n';

	import {
		ApiErr,
		listMessageTemplates,
		previewMessage,
		resetMessageTemplate,
		saveMessageTemplate,
		type MessageTemplate
	} from '$lib/api/client';
	import MessageBody from '$lib/components/MessageBody.svelte';
	import { confirmDialog } from '$lib/stores/confirm';
	import { pushToast } from '$lib/stores/toasts';

	let templates = $state<MessageTemplate[]>([]);
	let loading = $state(true);
	let openKey = $state<string | null>(null);

	// The draft belongs to the open row only: opening another discards it, deliberately, because
	// keeping N drafts alive invites saving one you had forgotten you were editing.
	let draftTitle = $state('');
	let draftBody = $state('');
	let tab = $state<'write' | 'preview'>('write');
	let previewHtml = $state<string | null>(null);
	let busy = $state(false);

	async function load(): Promise<void> {
		templates = await listMessageTemplates();
		loading = false;
	}

	onMount(load);

	/** Whether the draft still says what the row said when it was opened (10.F23). */
	function edited(t: MessageTemplate): boolean {
		return draftTitle !== t.title || draftBody !== t.body;
	}

	function open(t: MessageTemplate): void {
		if (openKey === t.key) {
			openKey = null;
			return;
		}
		openKey = t.key;
		draftTitle = t.title;
		draftBody = t.body;
		tab = 'write';
		previewHtml = null;
	}

	async function showPreview(): Promise<void> {
		tab = 'preview';
		previewHtml = await previewMessage(draftBody).catch(() => null);
	}

	async function save(t: MessageTemplate): Promise<void> {
		busy = true;
		try {
			await saveMessageTemplate(t.key, draftTitle, draftBody);
			await load();
			pushToast($_('admin.templates.saved'), 'success');
		} catch (err) {
			// The one refusal the server makes: a credential mail without the credential in it.
			const missing = err instanceof ApiErr && err.code === 'missing_placeholder';
			pushToast(
				missing ? $_('admin.templates.errorMissing') : $_('admin.templates.errorSave'),
				'error'
			);
		} finally {
			busy = false;
		}
	}

	async function reset(t: MessageTemplate): Promise<void> {
		const ok = await confirmDialog({
			title: $_('admin.templates.reset'),
			message: $_('admin.templates.confirmReset'),
			confirmLabel: $_('admin.templates.reset'),
			danger: true
		});
		if (!ok) return;
		busy = true;
		try {
			await resetMessageTemplate(t.key);
			await load();
			const fresh = templates.find((x) => x.key === t.key);
			if (fresh && openKey === t.key) {
				draftTitle = fresh.title;
				draftBody = fresh.body;
				previewHtml = null;
			}
		} catch {
			pushToast($_('admin.templates.errorSave'), 'error');
		} finally {
			busy = false;
		}
	}

	// Placeholders as chips that insert themselves: typing `{deletion_due_date}` by hand is how
	// an unknown placeholder gets into an override in the first place (ADMSG-R8).
	function insert(name: string): void {
		draftBody = `${draftBody}{${name}}`;
	}

	const inputClass =
		'w-full rounded border border-slate-300 px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-900';
</script>

<div class="space-y-3">
	<p class="max-w-prose text-sm text-slate-500">{$_('admin.templates.intro')}</p>

	{#if loading}
		<p class="text-sm text-slate-500">{$_('common.loading')}</p>
	{:else}
		<ul class="divide-y divide-slate-100 dark:divide-slate-800/60">
			{#each templates as t (t.key)}
				<li class="py-2">
					<button
						onclick={() => open(t)}
						class="flex w-full items-center gap-3 py-1 text-left text-sm hover:bg-slate-50 dark:hover:bg-slate-900/40"
					>
						<span class="flex-1 font-medium">{t.title}</span>
						<span class="font-mono text-xs text-slate-400">{t.key}</span>
						<span
							class="rounded px-1.5 py-0.5 text-xs {t.is_override
								? 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300'
								: 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400'}"
						>
							{t.is_override ? $_('admin.templates.custom') : $_('admin.templates.default')}
						</span>
					</button>

					{#if openKey === t.key}
						<div class="mt-3 space-y-3 pl-2">
							<label class="block space-y-1 text-sm">
								<span class="text-slate-500">{$_('admin.templates.titleLabel')}</span>
								<input bind:value={draftTitle} maxlength="200" class={inputClass} />
							</label>

							<div class="flex flex-wrap items-center gap-2 text-xs">
								<span class="text-slate-500">{$_('admin.templates.placeholders')}</span>
								{#each t.placeholders as name (name)}
									<button
										type="button"
										onclick={() => insert(name)}
										class="rounded border border-slate-300 px-1.5 py-0.5 font-mono hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800"
										>&#123;{name}&#125;{#if t.required.includes(name)}&nbsp;*{/if}</button
									>
								{/each}
							</div>
							{#if t.required.length > 0}
								<p class="text-xs text-amber-600 dark:text-amber-400">
									{$_('admin.templates.requiredHint')}
								</p>
							{/if}
							{#if t.unknown_placeholders.length > 0}
								<p class="text-xs text-amber-600 dark:text-amber-400">
									{$_('admin.templates.unknownHint', {
										values: { names: t.unknown_placeholders.join(', ') }
									})}
								</p>
							{/if}

							<div>
								<div class="flex gap-1 border-b border-slate-200 text-sm dark:border-slate-800">
									<button
										onclick={() => (tab = 'write')}
										class="rounded-t px-3 py-1.5 {tab === 'write'
											? 'border border-b-transparent border-slate-200 font-medium dark:border-slate-800'
											: 'text-slate-500'}"
									>
										{$_('admin.messages.tabWrite')}
									</button>
									<button
										onclick={showPreview}
										class="rounded-t px-3 py-1.5 {tab === 'preview'
											? 'border border-b-transparent border-slate-200 font-medium dark:border-slate-800'
											: 'text-slate-500'}"
									>
										{$_('admin.messages.tabPreview')}
									</button>
								</div>
								{#if tab === 'write'}
									<textarea
										bind:value={draftBody}
										rows="10"
										maxlength="20000"
										class="w-full rounded-b border border-slate-300 p-3 font-mono text-sm dark:border-slate-700 dark:bg-slate-900"
									></textarea>
								{:else}
									<div
										class="min-h-[10rem] rounded-b border border-slate-300 p-3 dark:border-slate-700 dark:bg-slate-900"
									>
										<MessageBody html={previewHtml} text={draftBody} />
									</div>
								{/if}
							</div>

							<div class="flex flex-wrap items-center gap-3 text-sm">
								<!-- Save also waits for an actual edit (10.F23): opening a row fills the
								     draft with the text in force, so an untouched form would otherwise
								     offer to store the wording as an override that changes nothing —
								     and the badge next to the key would start saying "rewritten". -->
								<button
									onclick={() => save(t)}
									disabled={busy || !draftTitle.trim() || !draftBody.trim() || !edited(t)}
									class="rounded bg-indigo-600 px-4 py-1.5 text-white hover:bg-indigo-500 disabled:opacity-40"
								>
									{$_('common.save')}
								</button>
								{#if t.is_override}
									<button
										onclick={() => reset(t)}
										disabled={busy}
										class="rounded border border-slate-300 px-3 py-1.5 hover:bg-slate-100 disabled:opacity-40 dark:border-slate-700 dark:hover:bg-slate-800"
									>
										{$_('admin.templates.reset')}
									</button>
								{/if}
							</div>
						</div>
					{/if}
				</li>
			{/each}
		</ul>
	{/if}
</div>
