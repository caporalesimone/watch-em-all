<script lang="ts">
	import { onMount } from 'svelte';
	import { _ } from 'svelte-i18n';

	import { listNotifiers } from '$lib/api/client';
	import Banner from '$lib/components/Banner.svelte';
	import PageTitle from '$lib/components/PageTitle.svelte';
	import { auth } from '$lib/stores/auth';

	// Dashboard hint (7.F4): in-app is always on, so the banner only nudges the user to add an
	// external channel (e.g. email) when none is active. It never means "you get nothing".
	let noExternalChannel = $state(false);
	onMount(async () => {
		try {
			const channels = await listNotifiers();
			noExternalChannel = !channels.some((c) => c.active && !c.is_in_app);
		} catch {
			/* non-blocking: the banner just stays hidden */
		}
	});
</script>

<div class="space-y-8">
	<PageTitle title={$_('dashboard.title')} />
	{#if $auth.user}
		<p>{$_('dashboard.welcome', { values: { name: $auth.user.first_name } })}</p>
	{/if}

	{#if noExternalChannel}
		<div class="max-w-xl">
			<Banner variant="info" icon="🔔" title={$_('dashboard.noChannelTitle')}>
				<p>
					{$_('dashboard.noChannelBody')}
					<a href="/profile" class="font-medium underline">{$_('dashboard.noChannelLink')}</a>
				</p>
			</Banner>
		</div>
	{/if}

	<p class="text-slate-500 dark:text-slate-400">{$_('dashboard.empty')}</p>
</div>
