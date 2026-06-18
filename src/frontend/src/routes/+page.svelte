<script lang="ts">
	import { _ } from 'svelte-i18n';

	import PageTitle from '$lib/components/PageTitle.svelte';
	import { auth } from '$lib/stores/auth';
</script>

<div class="space-y-8">
	<PageTitle title={$_('dashboard.title')} />
	{#if $auth.user}
		<p>{$_('dashboard.welcome', { values: { name: $auth.user.first_name } })}</p>
	{/if}
	<p class="text-slate-500 dark:text-slate-400">{$_('dashboard.empty')}</p>
</div>
