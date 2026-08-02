<!--
	Per-channel delivery outcomes for one notification (7.F5, reused by 10.F10). Extracted when
	announcements got a detail page of their own: the same list, about the same channels, and
	two copies of it would have started disagreeing about what "skipped" looks like.
-->
<script lang="ts">
	import { _ } from 'svelte-i18n';

	import type { AlertDelivery } from '$lib/api/client';

	let { deliveries }: { deliveries: AlertDelivery[] } = $props();

	function channelLabel(pluginId: string): string {
		if (pluginId === 'in_app') return $_('alerts.channelInApp');
		if (pluginId === 'email') return $_('alerts.channelEmail');
		return pluginId;
	}

	const STATUS: Record<string, string> = {
		delivered: 'alerts.deliveryDelivered',
		pending: 'alerts.deliveryPending',
		failed: 'alerts.deliveryFailed',
		skipped: 'alerts.deliverySkipped'
	};

	function statusClass(status: string): string {
		if (status === 'delivered')
			return 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300';
		if (status === 'failed') return 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300';
		return 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400';
	}
</script>

{#if deliveries.length > 0}
	<div class="space-y-2 border-t border-slate-200 pt-4 dark:border-slate-800">
		<h2 class="text-sm font-medium text-slate-500">{$_('alerts.deliveriesTitle')}</h2>
		<ul class="space-y-1 text-sm">
			{#each deliveries as d (d.plugin_id)}
				{#if d.status === 'skipped_no_notifier'}
					<li class="text-slate-400">{$_('alerts.deliveryNone')}</li>
				{:else}
					<li class="flex flex-wrap items-center gap-2">
						<span>{channelLabel(d.plugin_id)}</span>
						<span class="rounded px-1.5 py-0.5 text-xs {statusClass(d.status)}">
							{$_(STATUS[d.status] ?? d.status)}
						</span>
						{#if d.error}<span class="text-xs text-red-500">{d.error}</span>{/if}
					</li>
				{/if}
			{/each}
		</ul>
	</div>
{/if}
