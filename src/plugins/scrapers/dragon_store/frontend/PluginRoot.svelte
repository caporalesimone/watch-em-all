<script lang="ts">
	import { onDestroy, onMount } from 'svelte';

	import { apiFetch } from '$lib/auth/manager';
	import { _ } from '$lib/i18n';

	const BASE = '/api/plugins/dragon-store';

	interface Watch {
		id: number;
		kind: string;
		url: string;
	}
	interface PreviewProduct {
		external_id: string;
		name: string;
		url: string;
		price_current: string;
		currency: string;
		is_available: boolean;
	}
	interface ScrapeStatus {
		available: boolean;
		available_at: string | null;
		retry_after_seconds: number;
		interval_seconds: number;
	}

	let watches = $state<Watch[]>([]);
	let url = $state('');
	let preview = $state<PreviewProduct[] | null>(null);
	let status = $state<ScrapeStatus | null>(null);
	let remaining = $state(0);
	let confirming = $state(false);
	let busy = $state(false);
	let notice = $state<string | null>(null);
	let error = $state<string | null>(null);

	let timer: ReturnType<typeof setInterval> | undefined;

	async function getJson<T>(path: string): Promise<T> {
		const res = await apiFetch(path);
		if (!res.ok) throw new Error(String(res.status));
		return (await res.json()) as T;
	}

	async function loadWatches(): Promise<void> {
		watches = await getJson<Watch[]>(`${BASE}/watches`);
	}

	function applyStatus(s: ScrapeStatus): void {
		status = s;
		remaining = s.available ? 0 : s.retry_after_seconds;
	}

	async function loadStatus(): Promise<void> {
		applyStatus(await getJson<ScrapeStatus>(`${BASE}/scrape-now`));
	}

	onMount(() => {
		void loadWatches();
		void loadStatus();
		timer = setInterval(() => {
			if (status && !status.available && remaining > 0) {
				remaining -= 1;
				if (remaining <= 0) void loadStatus();
			}
		}, 1000);
	});
	onDestroy(() => {
		if (timer) clearInterval(timer);
	});

	async function addWatch(event: Event): Promise<void> {
		event.preventDefault();
		error = null;
		notice = null;
		if (!url.trim()) {
			error = $_('dragon_store.watches.invalid');
			return;
		}
		const res = await apiFetch(`${BASE}/watches`, {
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify({ url: url.trim() })
		});
		if (!res.ok) {
			error = $_('dragon_store.error');
			return;
		}
		url = '';
		preview = null;
		await loadWatches();
	}

	async function removeWatch(id: number): Promise<void> {
		const res = await apiFetch(`${BASE}/watches/${id}`, { method: 'DELETE' });
		if (res.ok) await loadWatches();
	}

	async function runPreview(): Promise<void> {
		error = null;
		notice = null;
		if (!url.trim()) {
			error = $_('dragon_store.watches.invalid');
			return;
		}
		busy = true;
		try {
			const res = await apiFetch(`${BASE}/test`, {
				method: 'POST',
				headers: { 'content-type': 'application/json' },
				body: JSON.stringify({ url: url.trim() })
			});
			if (!res.ok) throw new Error(String(res.status));
			preview = (await res.json()) as PreviewProduct[];
		} catch {
			error = $_('dragon_store.error');
		} finally {
			busy = false;
		}
	}

	async function doScrape(): Promise<void> {
		confirming = false;
		busy = true;
		error = null;
		notice = null;
		try {
			const res = await apiFetch(`${BASE}/scrape-now`, { method: 'POST' });
			if (res.status === 202) {
				notice = $_('dragon_store.scrape_now.started');
			} else if (res.status !== 429) {
				error = $_('dragon_store.error');
			}
			await loadStatus(); // refresh cooldown either way (202 -> on cooldown; 429 -> still)
		} catch {
			error = $_('dragon_store.error');
		} finally {
			busy = false;
		}
	}

	function fmt(total: number): string {
		const s = Math.max(0, Math.floor(total));
		const h = Math.floor(s / 3600);
		const m = Math.floor((s % 3600) / 60);
		const sec = s % 60;
		if (h > 0) return `${h}h ${String(m).padStart(2, '0')}m`;
		if (m > 0) return `${m}m ${String(sec).padStart(2, '0')}s`;
		return `${sec}s`;
	}

	function fmtInterval(total: number): string {
		const s = Math.floor(total);
		const h = Math.floor(s / 3600);
		const m = Math.floor((s % 3600) / 60);
		if (h > 0) return m > 0 ? `${h}h ${m}m` : `${h}h`;
		return m > 0 ? `${m}m` : `${s}s`;
	}

	const locked = $derived(status !== null && !status.available);
	const intervalLabel = $derived(status ? fmtInterval(status.interval_seconds) : '');

	const inputClass =
		'rounded border border-slate-300 bg-white px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-900';
	const btn =
		'rounded border border-slate-300 px-3 py-1 text-sm hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800';
</script>

<section class="space-y-8">
	<header class="space-y-4">
		<h1 class="text-xl font-semibold">{$_('dragon_store.title')}</h1>
		<p class="max-w-prose text-sm text-slate-500">{$_('dragon_store.blurb')}</p>
	</header>

	<!-- Add a watch + dry-run preview (3.F3 / 3.F4) -->
	<form onsubmit={addWatch} class="space-y-3">
		<div class="flex gap-2">
			<input
				class="{inputClass} flex-1"
				placeholder={$_('dragon_store.watches.url_placeholder')}
				bind:value={url}
			/>
			<button type="button" class={btn} onclick={runPreview} disabled={busy}>
				{$_('dragon_store.dry_run.action')}
			</button>
			<button
				type="submit"
				class="rounded bg-slate-800 px-3 py-1 text-sm text-white hover:bg-slate-700 disabled:opacity-50 dark:bg-slate-200 dark:text-slate-900 dark:hover:bg-white"
				disabled={busy}
			>
				{$_('dragon_store.watches.add')}
			</button>
		</div>
		<p class="text-xs text-slate-400">{$_('dragon_store.dry_run.hint')}</p>
	</form>

	{#if notice}<p class="text-sm text-green-600 dark:text-green-400">{notice}</p>{/if}
	{#if error}<p class="text-sm text-red-500">{error}</p>{/if}

	{#if preview}
		<div class="space-y-2">
			<h2 class="text-sm font-semibold">{$_('dragon_store.dry_run.heading')}</h2>
			<table class="w-full text-left text-sm">
				<tbody>
					{#each preview as p (p.external_id)}
						<tr class="border-b border-slate-100 dark:border-slate-800/60">
							<td class="py-1 pr-4">{p.name}</td>
							<td class="py-1 pr-4 font-medium">€{p.price_current}</td>
							<td class="py-1 pr-4 text-slate-500">
								{p.is_available ? $_('dragon_store.available') : $_('dragon_store.unavailable')}
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}

	<!-- Watched products list (3.F3) -->
	<div class="space-y-2">
		<h2 class="text-sm font-semibold">{$_('dragon_store.watches.heading')}</h2>
		{#if watches.length === 0}
			<p class="text-sm text-slate-500">{$_('dragon_store.watches.empty')}</p>
		{:else}
			<ul class="space-y-1">
				{#each watches as w (w.id)}
					<li class="flex items-center justify-between gap-3 text-sm">
						<span class="truncate text-slate-600 dark:text-slate-300" title={w.url}>{w.url}</span>
						<button class="text-xs text-red-500 hover:underline" onclick={() => removeWatch(w.id)}>
							{$_('dragon_store.watches.remove')}
						</button>
					</li>
				{/each}
			</ul>
		{/if}
	</div>

	<!-- Scrape now (3.F4) — sober: label + caption countdown when on cooldown -->
	<div class="space-y-1">
		<button
			class="rounded bg-emerald-600 px-3 py-1.5 text-sm text-white hover:bg-emerald-500 disabled:opacity-50"
			onclick={() => (confirming = true)}
			disabled={locked || busy}
		>
			{$_('dragon_store.scrape_now.action')}
		</button>
		{#if locked}
			<p class="text-xs text-slate-500">
				{$_('dragon_store.scrape_now.cooldown_caption', { values: { time: fmt(remaining) } })}
			</p>
		{/if}
	</div>
</section>

{#if confirming}
	<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
		<div class="w-full max-w-sm space-y-4 rounded-lg bg-white p-5 shadow-lg dark:bg-slate-900">
			<h3 class="text-base font-semibold">{$_('dragon_store.scrape_now.confirm_title')}</h3>
			<p class="text-sm text-slate-500">
				{$_('dragon_store.scrape_now.confirm_body', { values: { interval: intervalLabel } })}
			</p>
			<div class="flex justify-end gap-2">
				<button class={btn} onclick={() => (confirming = false)}>{$_('common.cancel')}</button>
				<button
					class="rounded bg-emerald-600 px-3 py-1 text-sm text-white hover:bg-emerald-500"
					onclick={doScrape}
				>
					{$_('dragon_store.scrape_now.action')}
				</button>
			</div>
		</div>
	</div>
{/if}
