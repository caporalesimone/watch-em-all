<script lang="ts">
	import { goto } from '$app/navigation';
	import { _ } from 'svelte-i18n';

	import * as api from '$lib/api/client';
	import NotifierChannels from '$lib/components/NotifierChannels.svelte';
	import PageTitle from '$lib/components/PageTitle.svelte';
	import { auth, forceAnon, isAdmin as isAdminStore, setUser } from '$lib/stores/auth';
	import { theme } from '$lib/stores/theme';

	// Roles don't overlap: an admin governs and owns no carts/alerts, so the personal
	// notification channels have nothing to deliver — hide them from the admin profile.
	const isAdmin = $derived($isAdminStore);

	let current = $state('');
	let next = $state('');
	let confirm = $state('');
	let error = $state('');
	let busy = $state(false);

	// The notification address (10.F17). For everybody but the bootstrap admin it *is* the
	// username, so it is shown and not offered for editing: changing where your mail goes
	// would mean changing who you sign in as, which is an administrator's operation.
	let address = $state($auth.user?.notification_email ?? '');
	let addressBusy = $state(false);
	let addressMsg = $state('');
	const canEditAddress = $derived($auth.user?.email_editable === true);
	// Save waits for a real edit (10.F23). The box opens filled with the address in force, so
	// without this it offers to write back the value it is already showing.
	const addressChanged = $derived(address.trim() !== ($auth.user?.notification_email ?? ''));

	async function saveAddress(event: SubmitEvent): Promise<void> {
		event.preventDefault();
		addressBusy = true;
		addressMsg = '';
		try {
			const me = await api.patchMe({ contact_email: address });
			setUser(me);
			address = me.notification_email;
			addressMsg = $_('common.saved');
		} catch (err) {
			addressMsg =
				err instanceof api.ApiErr
					? $_(`errors.${err.code}`, { default: $_('errors.generic') })
					: $_('errors.generic');
		} finally {
			addressBusy = false;
		}
	}

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
	<PageTitle title={$_('profile.title')} />

	<section class="space-y-2 text-sm">
		<h2 class="font-medium">{$_('profile.account')}</h2>
		<div class="flex justify-between">
			<span class="text-slate-500 dark:text-slate-400">{$_('login.username')}</span>
			<span>{$auth.user?.username}</span>
		</div>
		<div class="flex justify-between">
			<span class="text-slate-500 dark:text-slate-400">{$_('profile.role')}</span>
			<span>{$auth.user?.role}</span>
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
			<span class="text-slate-500 dark:text-slate-400">{$_('profile.language')}</span>
			<span>{$_('profile.languageValue')}</span>
		</div>

		<!-- Where this account is reached (10.F17). One row for everybody, but only the bootstrap
		     admin gets a field: it is the single account whose username is not an address, so it
		     is the single one with something to fill in. -->
		{#if canEditAddress}
			<form onsubmit={saveAddress} class="space-y-1 pt-2">
				<span class="block text-slate-500 dark:text-slate-400">{$_('profile.notifyEmail')}</span>
				<div class="flex gap-2">
					<input
						type="email"
						bind:value={address}
						required
						placeholder="name@example.com"
						class="{field} flex-1"
					/>
					<button
						type="submit"
						disabled={addressBusy || !addressChanged}
						class="rounded border border-slate-300 px-3 py-1.5 hover:bg-slate-100 disabled:opacity-50 dark:border-slate-700 dark:hover:bg-slate-800"
					>
						{$_('common.save')}
					</button>
				</div>
				<p class="text-xs text-slate-500 dark:text-slate-400">
					{$_('profile.notifyEmailAdminHint')}
				</p>
				{#if addressMsg}<p class="text-xs text-slate-500">{addressMsg}</p>{/if}
			</form>
		{:else}
			<div class="flex justify-between">
				<span class="text-slate-500 dark:text-slate-400">{$_('profile.notifyEmail')}</span>
				<span>{$auth.user?.notification_email}</span>
			</div>
			<p class="text-xs text-slate-500 dark:text-slate-400">{$_('profile.notifyEmailHint')}</p>
		{/if}
	</section>

	<section class="space-y-2 text-sm">
		<h2 class="font-medium">{$_('profile.settings')}</h2>
		<div class="flex items-center justify-between">
			<span class="text-slate-500 dark:text-slate-400">{$_('profile.theme')}</span>
			<button
				class="rounded border border-slate-300 px-3 py-1 hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800"
				onclick={() => theme.toggle()}
			>
				{$theme === 'dark' ? `☾ ${$_('profile.themeDark')}` : `☀ ${$_('profile.themeLight')}`}
			</button>
		</div>
	</section>

	{#if !isAdmin}
		<NotifierChannels />
	{/if}

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
