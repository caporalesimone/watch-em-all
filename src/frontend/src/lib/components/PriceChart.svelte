<script lang="ts">
	// The one price-history chart (8.F1/8.F2), used for both the product and the cart series —
	// the parent passes a normalized `{t, value, available}[]` and the current range. A step line
	// (price flat between changes) with EXPLICIT gaps where `available=false` (never interpolated,
	// HIST-R2); Week/Month/All selector; hover tooltip; light/dark. Chart.js on canvas, registered
	// explicitly (lean). Animations are ON so range/data changes move smoothly, not in jumps.
	import {
		CategoryScale,
		Chart,
		LinearScale,
		LineController,
		LineElement,
		PointElement,
		Tooltip
	} from 'chart.js';
	import { onMount } from 'svelte';
	import { _ } from 'svelte-i18n';

	import type { HistoryRange } from '$lib/api/client';
	import { theme } from '$lib/stores/theme';

	Chart.register(LineController, LineElement, PointElement, LinearScale, CategoryScale, Tooltip);

	type ChartPoint = { t: string; value: number; available: boolean };

	let {
		points,
		range,
		onRangeChange,
		currency = 'EUR',
		loading = false
	}: {
		points: ChartPoint[];
		range: HistoryRange;
		onRangeChange: (r: HistoryRange) => void;
		currency?: string;
		loading?: boolean;
	} = $props();

	const RANGES: HistoryRange[] = ['week', 'month', 'all'];
	const SYMBOL: Record<string, string> = { EUR: '€', USD: '$', GBP: '£', CHF: 'CHF ' };

	let canvas = $state<HTMLCanvasElement | undefined>();
	let chart: Chart | null = null;

	function money(v: number): string {
		return `${SYMBOL[currency] ?? currency + ' '}${v.toFixed(2)}`;
	}

	function fmtDate(ms: number): string {
		return new Date(ms).toLocaleDateString(undefined, {
			day: 'numeric',
			month: 'short',
			year: '2-digit'
		});
	}

	// Change points → a stepped polyline with explicit gaps. Availability belongs to the interval
	// AFTER a point; an unavailable interval becomes a `null` break. The last interval extends to
	// now (the current price holds). x is kept strictly increasing on the vertical connectors so
	// the step renders cleanly.
	function stepped(pts: ChartPoint[]): { x: number; y: number | null }[] {
		const now = Date.now();
		const src = pts.map((p) => ({ t: Date.parse(p.t), value: p.value, available: p.available }));
		const out: { x: number; y: number | null }[] = [];
		let lastX = -Infinity;
		const push = (t: number, y: number | null) => {
			const x = t <= lastX ? lastX + 1 : t;
			out.push({ x, y });
			lastX = x;
		};
		for (let i = 0; i < src.length; i++) {
			const cur = src[i];
			const next = i + 1 < src.length ? src[i + 1].t : now;
			if (cur.available) {
				push(cur.t, cur.value);
				push(next, cur.value);
			} else if (out.length && out[out.length - 1].y !== null) {
				push(cur.t, null);
			}
		}
		return out;
	}

	function palette(dark: boolean) {
		return {
			line: '#6366f1',
			grid: dark ? 'rgba(148,163,184,0.15)' : 'rgba(100,116,139,0.15)',
			text: dark ? '#94a3b8' : '#64748b'
		};
	}

	function render(dark: boolean): void {
		if (!canvas) return;
		const p = palette(dark);
		const data = stepped(points);
		if (!chart) {
			chart = new Chart(canvas, {
				type: 'line',
				data: {
					datasets: [
						{
							data,
							borderColor: p.line,
							backgroundColor: p.line,
							spanGaps: false,
							pointRadius: 0,
							pointHoverRadius: 4,
							borderWidth: 2,
							tension: 0
						}
					]
				},
				options: {
					responsive: true,
					maintainAspectRatio: false,
					animation: { duration: 500, easing: 'easeInOutQuart' },
					interaction: { mode: 'index', intersect: false },
					scales: {
						x: {
							type: 'linear',
							grid: { color: p.grid },
							ticks: { color: p.text, maxTicksLimit: 6, callback: (v) => fmtDate(Number(v)) }
						},
						y: {
							grid: { color: p.grid },
							ticks: { color: p.text, callback: (v) => money(Number(v)) }
						}
					},
					plugins: {
						legend: { display: false },
						tooltip: {
							callbacks: {
								title: (items) => fmtDate(Number(items[0].parsed.x)),
								label: (item) =>
									item.parsed.y == null
										? $_('priceHistory.outOfStock')
										: money(Number(item.parsed.y))
							}
						}
					}
				}
			});
		} else {
			chart.data.datasets[0].data = data;
			chart.data.datasets[0].borderColor = p.line;
			const s = chart.options.scales as Record<
				string,
				{ grid: { color: string }; ticks: { color: string } }
			>;
			s.x.grid.color = p.grid;
			s.x.ticks.color = p.text;
			s.y.grid.color = p.grid;
			s.y.ticks.color = p.text;
			chart.update(); // animates the transition (smooth, not jumpy)
		}
	}

	// Destroy once, on unmount — NOT on every re-render, so chart.update() can animate in place.
	onMount(() => () => {
		chart?.destroy();
		chart = null;
	});

	$effect(() => {
		// Re-runs on points/theme change; the ternary reads $theme so it stays a tracked dep.
		render($theme === 'dark');
	});

	const btn =
		'rounded px-3 py-1 text-sm font-medium border border-slate-300 dark:border-slate-700 transition';
	const active = 'bg-indigo-600 text-white border-indigo-600';
</script>

<div class="space-y-3">
	<div class="flex gap-2">
		{#each RANGES as r (r)}
			<button
				type="button"
				class="{btn} {range === r ? active : ''}"
				onclick={() => onRangeChange(r)}
			>
				{$_(`priceHistory.range.${r}`)}
			</button>
		{/each}
	</div>

	<div class="relative h-72 w-full rounded-lg border border-slate-200 p-3 dark:border-slate-800">
		<!-- Canvas stays mounted so the chart instance survives data changes and can animate. -->
		<canvas bind:this={canvas}></canvas>
		{#if loading || points.length === 0}
			<div
				class="absolute inset-0 flex items-center justify-center rounded-lg bg-white/60 text-sm text-slate-400 dark:bg-slate-950/60"
			>
				{loading ? $_('common.loading') : $_('priceHistory.empty')}
			</div>
		{/if}
	</div>
</div>
