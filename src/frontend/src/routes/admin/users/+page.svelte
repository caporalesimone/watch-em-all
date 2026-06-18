<script lang="ts">
	import { onMount } from 'svelte';
	import { _ } from 'svelte-i18n';

	import { ApiErr, createUser, listUsers, type AdminUser, type NewUser } from '$lib/api/client';

	let users = $state<AdminUser[]>([]);
	let loading = $state(true);
	let submitting = $state(false);
	let error = $state<string | null>(null);
	let notice = $state<string | null>(null);

	const empty: NewUser = {
		username: '',
		first_name: '',
		last_name: '',
		role: 'user',
		temp_password: ''
	};
	let form = $state<NewUser>({ ...empty });

	async function refresh(): Promise<void> {
		users = await listUsers();
		loading = false;
	}

	onMount(() => void refresh());

	async function submit(event: Event): Promise<void> {
		event.preventDefault();
		error = null;
		notice = null;
		submitting = true;
		try {
			const created = await createUser(form);
			notice = $_('admin.users.created', { values: { username: created.username } });
			form = { ...empty };
			await refresh();
		} catch (err) {
			error =
				err instanceof ApiErr && err.code === 'username_taken'
					? $_('admin.users.errorTaken')
					: $_('admin.users.errorGeneric');
		} finally {
			submitting = false;
		}
	}

	function status(user: AdminUser): string {
		if (!user.is_active) return $_('admin.users.statusDisabled');
		if (user.must_change_password) return $_('admin.users.statusPending');
		return $_('admin.users.statusActive');
	}

	function lastLogin(user: AdminUser): string {
		return user.last_login_at
			? new Date(user.last_login_at).toLocaleString()
			: $_('admin.users.never');
	}

	const inputClass =
		'rounded border border-slate-300 bg-white px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-900';
</script>

<section class="space-y-6">
	<h1 class="text-xl font-semibold">{$_('admin.users.title')}</h1>

	<form onsubmit={submit} class="flex flex-wrap items-end gap-3">
		<label class="flex flex-col gap-1 text-xs text-slate-500">
			{$_('admin.users.username')}
			<input class={inputClass} bind:value={form.username} required autocomplete="off" />
		</label>
		<label class="flex flex-col gap-1 text-xs text-slate-500">
			{$_('admin.users.firstName')}
			<input class={inputClass} bind:value={form.first_name} required />
		</label>
		<label class="flex flex-col gap-1 text-xs text-slate-500">
			{$_('admin.users.lastName')}
			<input class={inputClass} bind:value={form.last_name} required />
		</label>
		<label class="flex flex-col gap-1 text-xs text-slate-500">
			{$_('admin.users.role')}
			<select class={inputClass} bind:value={form.role}>
				<option value="user">{$_('admin.users.roleUser')}</option>
				<option value="admin">{$_('admin.users.roleAdmin')}</option>
			</select>
		</label>
		<label class="flex flex-col gap-1 text-xs text-slate-500">
			{$_('admin.users.tempPassword')}
			<input
				class={inputClass}
				type="text"
				bind:value={form.temp_password}
				required
				minlength="8"
				autocomplete="off"
			/>
		</label>
		<button
			type="submit"
			disabled={submitting}
			class="rounded bg-slate-800 px-3 py-1.5 text-sm text-white hover:bg-slate-700 disabled:opacity-50 dark:bg-slate-200 dark:text-slate-900 dark:hover:bg-white"
		>
			{$_('admin.users.submit')}
		</button>
	</form>
	{#if notice}<p class="text-sm text-green-600 dark:text-green-400">{notice}</p>{/if}
	{#if error}<p class="text-sm text-red-500">{error}</p>{/if}

	{#if loading}
		<p class="text-sm text-slate-500">{$_('common.loading')}</p>
	{:else}
		<table class="w-full text-left text-sm">
			<thead class="border-b border-slate-200 text-xs text-slate-500 dark:border-slate-800">
				<tr>
					<th class="py-2 pr-4">{$_('admin.users.username')}</th>
					<th class="py-2 pr-4">{$_('admin.users.colName')}</th>
					<th class="py-2 pr-4">{$_('admin.users.colRole')}</th>
					<th class="py-2 pr-4">{$_('admin.users.colStatus')}</th>
					<th class="py-2 pr-4">{$_('admin.users.colLastLogin')}</th>
				</tr>
			</thead>
			<tbody>
				{#each users as user (user.id)}
					<tr class="border-b border-slate-100 dark:border-slate-800/60">
						<td class="py-2 pr-4 font-medium">{user.username}</td>
						<td class="py-2 pr-4">{user.first_name} {user.last_name}</td>
						<td class="py-2 pr-4">{user.role}</td>
						<td class="py-2 pr-4">{status(user)}</td>
						<td class="py-2 pr-4 text-slate-500">{lastLogin(user)}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	{/if}
</section>
