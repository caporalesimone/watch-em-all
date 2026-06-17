<script lang="ts">
	import { _ } from 'svelte-i18n';

	import { auth } from '$lib/stores/auth';
</script>

<div class="space-y-3">
	<h1 class="text-2xl font-semibold">{$_('dashboard.title')}</h1>
	{#if $auth.user}
		<p>{$_('dashboard.welcome', { values: { username: $auth.user.username } })}</p>
	{/if}
	<p class="text-slate-500 dark:text-slate-400">{$_('dashboard.empty')}</p>
</div>
