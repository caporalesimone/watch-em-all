<script lang="ts">
	import { _ } from 'svelte-i18n';

	import { ApiErr } from '$lib/api/client';
	import { signIn } from '$lib/stores/auth';

	let username = $state('');
	let password = $state('');
	let error = $state('');
	let busy = $state(false);

	const field =
		'w-full rounded border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900';

	async function submit(event: SubmitEvent): Promise<void> {
		event.preventDefault();
		error = '';
		busy = true;
		try {
			await signIn(username, password);
		} catch (err) {
			error =
				err instanceof ApiErr
					? $_(`errors.${err.code}`, { default: $_('errors.generic') })
					: $_('errors.generic');
		} finally {
			busy = false;
		}
	}
</script>

<form
	onsubmit={submit}
	class="w-full max-w-sm space-y-4 rounded-lg border border-slate-200 p-6 dark:border-slate-800"
>
	<h1 class="text-xl font-semibold">{$_('login.title')}</h1>
	<label class="block text-sm">
		<span class="mb-1 block text-slate-600 dark:text-slate-300">{$_('login.username')}</span>
		<input name="username" bind:value={username} autocomplete="username" required class={field} />
	</label>
	<label class="block text-sm">
		<span class="mb-1 block text-slate-600 dark:text-slate-300">{$_('login.password')}</span>
		<input
			type="password"
			name="password"
			bind:value={password}
			autocomplete="current-password"
			required
			class={field}
		/>
	</label>
	{#if error}
		<p class="text-sm text-red-600 dark:text-red-400">{error}</p>
	{/if}
	<button
		type="submit"
		disabled={busy}
		class="w-full rounded bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
	>
		{$_('login.submit')}
	</button>
</form>
