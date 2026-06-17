<script lang="ts">
	import { _ } from 'svelte-i18n';

	import { theme } from '$lib/stores/theme';
</script>

<header
	class="flex items-center justify-end border-b border-slate-200 px-4 py-3 dark:border-slate-800"
>
	<button
		class="rounded px-3 py-1 text-sm hover:bg-slate-200 dark:hover:bg-slate-800"
		title={$_('theme.toggle')}
		aria-label={$_('theme.toggle')}
		onclick={() => theme.toggle()}
	>
		{$theme === 'dark' ? '☀' : '☾'}
	</button>
</header>
