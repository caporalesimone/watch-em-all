<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { _ } from 'svelte-i18n';

	import * as api from '$lib/api/client';
	import { auth, forceAnon, signIn } from '$lib/stores/auth';

	let next = $state('');
	let confirm = $state('');
	let error = $state('');
	let busy = $state(false);
	let newPasswordInput: HTMLInputElement | undefined = $state();

	// Autofocus the first field (new password) when the forced-change page opens.
	onMount(() => newPasswordInput?.focus());

	const field =
		'w-full rounded border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900';

	async function submit(event: SubmitEvent): Promise<void> {
		event.preventDefault();
		error = '';
		if (next !== confirm) {
			error = $_('changePassword.mismatch');
			return;
		}
		busy = true;
		// Capture the username before the change: the re-login below refreshes the store.
		const username = $auth.user?.username ?? '';
		try {
			// Forced first change: the current password is not required (auth.md).
			await api.changePassword(next);
		} catch (err) {
			error =
				err instanceof api.ApiErr
					? $_(`errors.${err.code}`, { default: $_('errors.generic') })
					: $_('errors.generic');
			busy = false;
			return;
		}
		// AUTH-R5: the change invalidated every token. The user just typed the new
		// password, so sign straight back in and let the route guard land them on
		// their home — no detour through the login page. If the re-login somehow
		// fails, fall back to /login.
		try {
			await signIn(username, next);
		} catch {
			forceAnon();
			await goto('/login');
		} finally {
			busy = false;
		}
	}
</script>

<form
	onsubmit={submit}
	class="w-full max-w-sm space-y-4 rounded-lg border border-slate-200 p-6 dark:border-slate-800"
>
	<h1 class="text-xl font-semibold">{$_('changePassword.title')}</h1>
	{#if $auth.user}
		<p class="text-sm text-slate-500 dark:text-slate-400">
			{$_('changePassword.greeting', { values: { name: $auth.user.first_name } })}
		</p>
	{/if}
	<!-- Hidden username field so password managers associate the new password. -->
	<input
		type="text"
		name="username"
		autocomplete="username"
		value={$auth.user?.username ?? ''}
		readonly
		tabindex="-1"
		aria-hidden="true"
		class="sr-only"
	/>
	<label class="block text-sm">
		<span class="mb-1 block text-slate-600 dark:text-slate-300">{$_('changePassword.new')}</span>
		<input
			type="password"
			name="new-password"
			bind:value={next}
			bind:this={newPasswordInput}
			autocomplete="new-password"
			required
			minlength="8"
			class={field}
		/>
	</label>
	<label class="block text-sm">
		<span class="mb-1 block text-slate-600 dark:text-slate-300">{$_('changePassword.confirm')}</span
		>
		<input
			type="password"
			name="confirm-password"
			bind:value={confirm}
			autocomplete="new-password"
			required
			minlength="8"
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
		{$_('changePassword.submit')}
	</button>
</form>
