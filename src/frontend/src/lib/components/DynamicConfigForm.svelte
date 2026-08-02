<script lang="ts">
	// Dynamic config form (7.F1/7.F2): renders ONE form from a plugin's `list[ConfigField]`, for
	// both the admin and user config of any notifier — the core never hard-codes a field. Secret
	// fields are masked and write-only (CFG-R3): shown empty with an "is set" hint; left blank on
	// submit means "keep the stored value" (the key is simply not sent). Labels come from the
	// field's i18n key, falling back to a humanized key (V1 is English; backend notifiers ship no
	// frontend namespace). Self-contained and props-driven (FE-18) — reused wherever config is edited.
	import { _ } from 'svelte-i18n';

	import type { ConfigField } from '$lib/api/client';
	import { changed, snapshot } from '$lib/forms';

	let {
		schema,
		config = {},
		isSet = {},
		busy = false,
		submitLabel,
		onSubmit
	}: {
		schema: ConfigField[];
		config?: Record<string, unknown>;
		isSet?: Record<string, boolean>;
		busy?: boolean;
		submitLabel?: string;
		onSubmit: (values: Record<string, unknown>) => void | Promise<unknown>;
	} = $props();

	const ACRONYMS: Record<string, string> = {
		smtp: 'SMTP',
		tls: 'TLS',
		url: 'URL',
		id: 'ID',
		http: 'HTTP'
	};

	function humanize(key: string): string {
		return key
			.split('_')
			.map((w, i) => ACRONYMS[w] ?? (i === 0 ? w.charAt(0).toUpperCase() + w.slice(1) : w))
			.join(' ');
	}

	function label(f: ConfigField): string {
		return $_(f.label_key, { default: humanize(f.key) });
	}

	function help(f: ConfigField): string {
		return f.help_key ? $_(f.help_key, { default: '' }) : '';
	}

	// Local editable values, rebuilt whenever the schema/config change (e.g. after a save).
	let values = $state<Record<string, unknown>>({});
	// What Save compares against (10.F23). A secret starts blank and blank means "keep what is
	// stored", so an untouched form with a stored secret is genuinely unchanged — typing into
	// that box is the only thing that makes it dirty, which is the same rule the submit uses.
	let baseline = $state<Record<string, unknown>>({});
	let sig = '';
	$effect(() => {
		const next = JSON.stringify([schema.map((f) => f.key), config]);
		if (next === sig) return;
		sig = next;
		const v: Record<string, unknown> = {};
		for (const f of schema) {
			if (f.secret) v[f.key] = '';
			else v[f.key] = config[f.key] ?? f.default ?? (f.type === 'bool' ? false : '');
		}
		values = v;
		baseline = snapshot(v);
	});

	const dirty = $derived(changed(values, baseline));

	async function submit(event: SubmitEvent): Promise<void> {
		event.preventDefault();
		const out: Record<string, unknown> = {};
		for (const f of schema) {
			const val = values[f.key];
			if (f.secret) {
				// Absent/blank secret → do not send (keep the stored value, CFG-R3).
				if (typeof val === 'string' && val.trim() !== '') out[f.key] = val;
			} else if (f.type === 'number') {
				out[f.key] = val === '' || val == null ? null : Number(val);
			} else if (f.type === 'bool') {
				out[f.key] = Boolean(val);
			} else {
				out[f.key] = val ?? '';
			}
		}
		await onSubmit(out);
		// Clean again once the save has been made. Optimistic, and deliberately so: the pages that
		// own these forms report their own failures (a toast, a red line) and do not throw, so the
		// alternative would be a form that stays dirty for ever after one server hiccup. What the
		// admin typed is still in the boxes either way — touching a field re-arms Save.
		//
		// A secret goes back to blank, because that is what "keep the stored value" looks like and
		// the value is now stored.
		for (const f of schema) if (f.secret) values[f.key] = '';
		baseline = snapshot(values);
	}

	const field =
		'w-full rounded border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900';
</script>

<form onsubmit={submit} class="space-y-3">
	{#each schema as f (f.key)}
		<label class="block text-sm">
			<span class="mb-1 block text-slate-600 dark:text-slate-300">
				{label(f)}{#if f.required}<span class="text-red-500"> *</span>{/if}
			</span>

			{#if f.type === 'bool'}
				<input type="checkbox" bind:checked={values[f.key] as boolean} class="h-4 w-4" />
			{:else if f.type === 'select'}
				<select bind:value={values[f.key]} class={field}>
					{#each f.options ?? [] as opt (opt)}
						<option value={opt}>{opt}</option>
					{/each}
				</select>
			{:else if f.type === 'number'}
				<input type="number" bind:value={values[f.key]} class={field} />
			{:else if f.secret}
				<input
					type="password"
					bind:value={values[f.key]}
					autocomplete="new-password"
					placeholder={isSet[f.key] ? $_('notifiers.secretSet') : ''}
					class={field}
				/>
			{:else}
				<input
					type={f.type === 'email' ? 'email' : f.type === 'url' ? 'url' : 'text'}
					bind:value={values[f.key]}
					placeholder={f.placeholder ?? ''}
					class={field}
				/>
			{/if}

			{#if help(f)}<span class="mt-1 block text-xs text-slate-400">{help(f)}</span>{/if}
		</label>
	{/each}

	<button
		type="submit"
		disabled={busy || !dirty}
		class="rounded bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
	>
		{submitLabel ?? $_('common.save')}
	</button>
</form>
