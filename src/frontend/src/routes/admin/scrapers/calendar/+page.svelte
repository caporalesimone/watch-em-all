<script lang="ts">
	// The day at a glance (10.F12). Read-only on purpose: this page answers "what is going to
	// happen today", and the place to *change* it is the schedule editor — two pages that both
	// edit the same slots would eventually disagree about which one won.
	import { onMount } from 'svelte';
	import { _ } from 'svelte-i18n';

	import { getScraperCalendar, type CalendarSlot } from '$lib/api/client';
	import PageTitle from '$lib/components/PageTitle.svelte';
	import SourceTag from '$lib/components/SourceTag.svelte';

	function todayIso(): string {
		const now = new Date();
		const offset = now.getTimezoneOffset() * 60_000;
		return new Date(now.getTime() - offset).toISOString().slice(0, 10);
	}

	let day = $state(todayIso());
	let slots = $state<CalendarSlot[]>([]);
	let loading = $state(true);

	async function refresh(): Promise<void> {
		loading = true;
		slots = (await getScraperCalendar(day)).slots;
		loading = false;
	}

	onMount(() => void refresh());

	function clock(iso: string): string {
		return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
	}

	// The block is as wide as the run usually takes, so a heavy scraper *looks* heavy. Floored
	// at something visible: a ten-second run still has to be clickable.
	const MIN_PX = 24;
	const PX_PER_MINUTE = 6;
	function width(slot: CalendarSlot): number {
		if (slot.avg_seconds === null) return MIN_PX;
		return Math.max(MIN_PX, Math.round((slot.avg_seconds / 60) * PX_PER_MINUTE));
	}

	function duration(slot: CalendarSlot): string {
		if (slot.avg_seconds === null) return $_('admin.calendar.unknownDuration');
		return slot.avg_seconds < 60
			? `~${slot.avg_seconds}s`
			: `~${Math.round(slot.avg_seconds / 60)}m`;
	}
</script>

<section class="space-y-4">
	<PageTitle title={$_('admin.calendar.title')} />
	<p class="text-sm text-slate-500">{$_('admin.calendar.hint')}</p>

	<label class="flex items-center gap-2 text-sm">
		<span class="text-xs text-slate-500">{$_('admin.calendar.date')}</span>
		<input
			type="date"
			bind:value={day}
			onchange={() => void refresh()}
			class="rounded border border-slate-300 bg-white px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-900"
		/>
		<button
			type="button"
			class="rounded border border-slate-300 px-2 py-1 text-xs hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800"
			onclick={() => {
				day = todayIso();
				void refresh();
			}}>{$_('admin.calendar.today')}</button
		>
	</label>

	{#if loading}
		<p class="text-sm text-slate-500">{$_('common.loading')}</p>
	{:else if slots.length === 0}
		<p class="text-sm text-slate-500">{$_('admin.calendar.empty')}</p>
	{:else}
		<ol class="space-y-2">
			{#each slots as slot (`${slot.scraper_id}:${slot.at}`)}
				<li class="flex items-center gap-3 text-sm">
					<span class="w-14 font-mono text-slate-500">{clock(slot.at)}</span>
					<a
						href="/admin/scrapers/{slot.scraper_id}"
						class="flex items-center gap-2 rounded px-2 py-1 {slot.enabled
							? 'bg-slate-200 hover:bg-slate-300 dark:bg-slate-700 dark:hover:bg-slate-600'
							: 'border border-dashed border-slate-300 dark:border-slate-700'}"
						style="min-width: {width(slot)}px"
					>
						<SourceTag pluginId={slot.scraper_id} />
					</a>
					<span class="text-xs text-slate-400">
						{duration(slot)}{#if !slot.enabled}&nbsp;· {$_('admin.calendar.suspended')}{/if}
					</span>
				</li>
			{/each}
		</ol>
	{/if}
</section>
