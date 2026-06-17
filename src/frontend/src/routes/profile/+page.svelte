<script lang="ts">
	import { goto } from '$app/navigation';
	import { _ } from 'svelte-i18n';

	import * as api from '$lib/api/client';
	import { auth, forceAnon } from '$lib/stores/auth';

	let current = $state('');
	let next = $state('');
	let confirm = $state('');
	let error = $state('');
	let busy = $state(false);

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
		try {
			// Normal change: the current password is always required (auth.md).
			await api.changePassword(next, current);
			forceAnon(); // AUTH-R5: tokens invalidated → sign in again
			await goto('/login');
		} catch (err) {
			error =
				err instanceof api.ApiErr
					? $_(`errors.${err.code}`, { default: $_('errors.generic') })
					: $_('errors.generic');
		} finally {
			busy = false;
		}
	}
</script>

<div class="max-w-md space-y-8">
	<h1 class="text-2xl font-semibold">{$_('profile.title')}</h1>

	<section class="space-y-2 text-sm">
		<h2 class="font-medium">{$_('profile.account')}</h2>
		<div class="flex justify-between">
			<span class="text-slate-500 dark:text-slate-400">{$_('login.username')}</span>
			<span>{$auth.user?.username}</span>
		</div>
		<div class="flex justify-between">
			<span class="text-slate-500 dark:text-slate-400">{$_('profile.name')}</span>
			<span>{$auth.user?.first_name}</span>
		</div>
		<div class="flex justify-between">
			<span class="text-slate-500 dark:text-slate-400">{$_('profile.surname')}</span>
			<span>{$auth.user?.last_name}</span>
		</div>
		<div class="flex justify-between">
			<span class="text-slate-500 dark:text-slate-400">{$_('profile.role')}</span>
			<span>{$auth.user?.role}</span>
		</div>
		<div class="flex justify-between">
			<span class="text-slate-500 dark:text-slate-400">{$_('profile.language')}</span>
			<span>{$_('profile.languageValue')}</span>
		</div>
	</section>

	<form onsubmit={submit} class="space-y-4">
		<h2 class="font-medium">{$_('profile.changePassword')}</h2>
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
			<span class="mb-1 block text-slate-600 dark:text-slate-300"
				>{$_('changePassword.current')}</span
			>
			<input
				type="password"
				name="current-password"
				bind:value={current}
				autocomplete="current-password"
				required
				class={field}
			/>
		</label>
		<label class="block text-sm">
			<span class="mb-1 block text-slate-600 dark:text-slate-300">{$_('changePassword.new')}</span>
			<input
				type="password"
				name="new-password"
				bind:value={next}
				autocomplete="new-password"
				required
				minlength="8"
				class={field}
			/>
		</label>
		<label class="block text-sm">
			<span class="mb-1 block text-slate-600 dark:text-slate-300"
				>{$_('changePassword.confirm')}</span
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
			class="rounded bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
		>
			{$_('changePassword.submit')}
		</button>
	</form>
</div>
