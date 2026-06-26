<script lang="ts">
	// 24-hour schedule visualization (4.F1b). Six 4-hour bands from midnight; each scheduled
	// time is a clickable plugin-icon marker (click → remove that run). A "now" marker (a
	// badge + line) shows the current SERVER time: it is read once from /api/health at mount
	// and then ticked locally every second (no per-second API calls); on hover it highlights
	// the next upcoming run and shows when it will start. All computed client-side.
	import { onMount } from 'svelte';
	import { _ } from 'svelte-i18n';

	import { getHealth } from '$lib/api/client';

	type Scraper = {
		id: string;
		name: string;
		icon: string | null;
		times: string[]; // canonical HH:MM:SS
		enabled: boolean;
		schedulable: boolean;
	};

	let {
		scrapers,
		onRemove
	}: { scrapers: Scraper[]; onRemove: (id: string, time: string) => void } = $props();

	// TEMP(4.F1): prototype controls — decide a fixed value / whether to remove before the
	// Phase 4 closure (tracked in development-flow/phase-04). Not production config.
	let showTicks = $state(true);
	let markerSize = $state(16); // px, 8–24

	const BANDS = [0, 1, 2, 3, 4, 5];
	const SECONDS_PER_BAND = 4 * 3600;

	function pad(n: number): string {
		return String(n).padStart(2, '0');
	}

	function timeToSeconds(v: string): number | null {
		const m = /^(\d{1,2}):(\d{2})(?::(\d{2}))?$/.exec(v);
		if (!m) return null;
		const s = +m[1] * 3600 + +m[2] * 60 + (m[3] ? +m[3] : 0);
		return s >= 0 && s < 86400 ? s : null;
	}

	function bandLabel(b: number): string {
		return `${pad(b * 4)}:00 – ${pad(b * 4 + 4)}:00`;
	}

	// Position (%) of a seconds-of-day value inside its band.
	function posInBand(sec: number): number {
		const band = Math.floor(sec / SECONDS_PER_BAND);
		return ((sec - band * SECONDS_PER_BAND) / SECONDS_PER_BAND) * 100;
	}

	function humanize(s: number): string {
		if (s >= 3600) {
			const h = Math.floor(s / 3600);
			const m = Math.floor((s % 3600) / 60);
			return m ? `${h}h ${m}m` : `${h}h`;
		}
		if (s >= 60) {
			const m = Math.floor(s / 60);
			const ss = s % 60;
			return ss ? `${m}m ${ss}s` : `${m}m`;
		}
		return `${s}s`;
	}

	type Marker = { id: string; name: string; icon: string | null; time: string; sec: number };

	const markersByBand = $derived.by(() => {
		const out: Marker[][] = [[], [], [], [], [], []];
		for (const s of scrapers) {
			if (!s.schedulable) continue;
			for (const t of s.times) {
				const sec = timeToSeconds(t);
				if (sec === null) continue;
				out[Math.floor(sec / SECONDS_PER_BAND)].push({
					id: s.id,
					name: s.name,
					icon: s.icon,
					time: t,
					sec
				});
			}
		}
		for (const band of out) band.sort((a, b) => a.sec - b.sec);
		return out;
	});

	const totalRuns = $derived(
		scrapers.reduce((n, s) => n + (s.schedulable ? s.times.length : 0), 0)
	);

	function freqLabel(s: Scraper): string {
		const n = s.schedulable ? s.times.length : 0;
		return n > 0
			? $_('admin.scrapers.viz.perDay', { values: { n } })
			: $_('admin.scrapers.viz.noRuns');
	}

	// --- server clock: read once, tick locally each second ---
	let serverSkewMs = $state(0); // server_now - client_now at load
	let tzOffsetMin = $state(-new Date().getTimezoneOffset()); // fallback: client TZ
	let nowSec = $state(0); // seconds-of-day in the server TZ
	let hasClock = $state(false);
	let hovering = $state(false);

	function parseOffsetMinutes(iso: string): number {
		const m = /([+-])(\d{2}):(\d{2})$/.exec(iso);
		if (m) return (m[1] === '-' ? -1 : 1) * (+m[2] * 60 + +m[3]);
		return 0; // trailing Z or no offset → UTC
	}

	function recomputeNow(): void {
		const wall = Math.floor((Date.now() + serverSkewMs) / 1000) + tzOffsetMin * 60;
		nowSec = ((wall % 86400) + 86400) % 86400;
	}

	onMount(() => {
		let cancelled = false;
		getHealth()
			.then((h) => {
				if (cancelled || !h.server_time) return;
				const epoch = Date.parse(h.server_time);
				if (!Number.isNaN(epoch)) {
					serverSkewMs = epoch - Date.now();
					tzOffsetMin = parseOffsetMinutes(h.server_time);
					hasClock = true;
				}
			})
			.catch(() => {
				/* health down → fall back to the client clock */
				hasClock = true;
			});
		recomputeNow();
		const timer = setInterval(recomputeNow, 1000);
		return () => {
			cancelled = true;
			clearInterval(timer);
		};
	});

	const nowBand = $derived(Math.floor(nowSec / SECONDS_PER_BAND));
	const nowPos = $derived(posInBand(nowSec));
	const nowLabel = $derived(
		`${pad(Math.floor(nowSec / 3600))}:${pad(Math.floor((nowSec % 3600) / 60))}:${pad(nowSec % 60)}`
	);

	// Next upcoming run among enabled scrapers (smallest positive wrap-around delta).
	const nextRun = $derived.by(() => {
		let best: { id: string; name: string; time: string; delta: number } | null = null;
		for (const s of scrapers) {
			if (!s.schedulable || !s.enabled) continue;
			for (const t of s.times) {
				const sec = timeToSeconds(t);
				if (sec === null) continue;
				const delta = (((sec - nowSec) % 86400) + 86400) % 86400;
				if (best === null || delta < best.delta) best = { id: s.id, name: s.name, time: t, delta };
			}
		}
		return best;
	});

	function isNext(m: Marker): boolean {
		return hovering && nextRun !== null && nextRun.id === m.id && nextRun.time === m.time;
	}
</script>

<section class="rounded-xl border border-slate-200 p-6 dark:border-slate-800/80">
	<div class="flex flex-wrap items-baseline justify-between gap-4">
		<div>
			<h2 class="text-lg font-semibold">{$_('admin.scrapers.viz.title')}</h2>
			<p class="text-sm text-slate-500">{$_('admin.scrapers.viz.subtitle')}</p>
		</div>
		<span class="font-mono text-sm text-slate-400">
			{$_('admin.scrapers.viz.runsPerDay', { values: { n: totalRuns } })}
		</span>
	</div>

	<!-- legend -->
	<div class="mt-4 flex flex-wrap gap-x-5 gap-y-2">
		{#each scrapers as s (s.id)}
			<span class="flex items-center gap-2 text-sm">
				{#if s.icon}
					<img src={s.icon} alt="" class="h-3.5 w-3.5" />
				{:else}
					<span class="inline-block h-2.5 w-2.5 rounded-full bg-slate-400"></span>
				{/if}
				<span class="text-slate-600 dark:text-slate-300">{s.name}</span>
				<span class="font-mono text-xs text-slate-400">{freqLabel(s)}</span>
			</span>
		{/each}
	</div>

	<!-- TEMP(4.F1) prototype controls -->
	<div class="mt-3 flex flex-wrap items-center gap-5 text-xs text-slate-500">
		<label class="flex items-center gap-2">
			<input type="checkbox" bind:checked={showTicks} />
			{$_('admin.scrapers.viz.showTicks')}
		</label>
		<label class="flex items-center gap-2">
			{$_('admin.scrapers.viz.markerSize')}
			<input type="range" min="8" max="24" bind:value={markerSize} />
		</label>
	</div>

	{#if totalRuns === 0}
		<div
			class="mt-6 rounded-lg border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500 dark:border-slate-700"
		>
			{$_('admin.scrapers.viz.empty')}
		</div>
	{:else}
		<div class="mt-5 flex flex-col gap-3.5">
			{#each BANDS as band (band)}
				<div class="flex items-stretch gap-4">
					<div class="w-24 shrink-0 self-center font-mono text-[13px] text-slate-500">
						{bandLabel(band)}
					</div>
					<div class="relative h-14 flex-1">
						<!-- baseline -->
						<div
							class="absolute right-0 left-0 bg-slate-200 dark:bg-white/10"
							style="top:26px;height:1px"
						></div>

						<!-- hour ticks -->
						{#if showTicks}
							{#each [0, 1, 2, 3, 4] as i (i)}
								<div
									class="absolute bg-slate-300 dark:bg-white/10"
									style="left:{i * 25}%;top:19px;width:1px;height:14px"
								></div>
								<div
									class="absolute -translate-x-1/2 font-mono text-[10px] text-slate-400"
									style="left:{i * 25}%;top:36px"
								>
									{pad(band * 4 + i)}
								</div>
							{/each}
						{/if}

						<!-- markers (plugin icons) -->
						{#each markersByBand[band] as m (m.id + m.time)}
							<button
								type="button"
								class="absolute z-10 -translate-x-1/2 -translate-y-1/2 rounded-full ring-1 ring-white/25 transition-transform hover:brightness-110"
								class:scale-125={isNext(m)}
								class:ring-2={isNext(m)}
								class:ring-amber-400={isNext(m)}
								class:z-20={isNext(m)}
								style="left:{posInBand(
									m.sec
								)}%;top:26px;width:{markerSize}px;height:{markerSize}px;box-shadow:0 2px 6px rgba(0,0,0,0.5)"
								title={$_('admin.scrapers.viz.removeTitle', {
									values: { name: m.name, time: m.time }
								})}
								onclick={() => onRemove(m.id, m.time)}
							>
								{#if m.icon}
									<img
										src={m.icon}
										alt=""
										class="h-full w-full rounded-full bg-slate-900 object-contain p-0.5"
									/>
								{:else}
									<span class="block h-full w-full rounded-full bg-slate-400"></span>
								{/if}
							</button>
						{/each}

						<!-- now marker (badge + line); position from the server clock -->
						{#if hasClock && nowBand === band}
							<!-- Button (not a static div) so the hover/focus that reveals the next run is
							     keyboard-accessible; it has no click action (cursor-default, transparent). -->
							<button
								type="button"
								class="absolute top-0 bottom-0 z-30 cursor-default border-0 bg-transparent p-0"
								style="left:{nowPos}%"
								aria-label={nowLabel}
								onmouseenter={() => (hovering = true)}
								onmouseleave={() => (hovering = false)}
								onfocus={() => (hovering = true)}
								onblur={() => (hovering = false)}
							>
								<div
									class="absolute inset-y-0 -translate-x-1/2 bg-slate-400 dark:bg-slate-300"
									style="width:2px"
								></div>
								<div
									class="absolute top-1 -translate-x-1/2 rounded bg-white px-1.5 py-0.5 font-mono text-[11px] whitespace-nowrap text-slate-800 shadow"
								>
									{nowLabel}
								</div>
								{#if hovering && nextRun}
									<div
										class="absolute -top-6 -translate-x-1/2 rounded bg-slate-900 px-2 py-1 text-xs whitespace-nowrap text-white shadow-lg"
									>
										{$_('admin.scrapers.viz.willStartIn', {
											values: { name: nextRun.name, when: humanize(nextRun.delta) }
										})}
									</div>
								{/if}
							</button>
						{/if}
					</div>
				</div>
			{/each}
		</div>
	{/if}
</section>
