<script lang="ts">
	import { onMount } from 'svelte';
	import { _ } from 'svelte-i18n';

	import {
		ApiErr,
		createUser,
		getSettings,
		listUsers,
		markUserForDeletion,
		resetUserPassword,
		restoreUser,
		setUserActive,
		type AdminUser,
		type NewUser,
		type UserSort,
		type UserStatusFilter
	} from '$lib/api/client';
	import PageTitle from '$lib/components/PageTitle.svelte';
	import { auth } from '$lib/stores/auth';

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

	// List controls (10.F1). The sort exists to answer "who has stopped using this", so the
	// default stays alphabetical and the dormancy question is one click away.
	let statusFilter = $state<UserStatusFilter | null>(null);
	// Read once for the delete confirmation, which has to name a date before the server has
	// computed one. The server stays the authority: this only previews it.
	let graceDays = $state(30);
	let sort = $state<UserSort>('username');
	let order = $state<'asc' | 'desc'>('asc');

	async function refresh(): Promise<void> {
		users = await listUsers({ status: statusFilter, sort, order });
		loading = false;
	}

	onMount(() => {
		void refresh();
		void getSettings()
			.then((s) => (graceDays = s.user_deletion_retention_days))
			.catch(() => undefined); // a stale preview is better than a broken page
	});

	function sortBy(column: UserSort): void {
		if (sort === column) {
			order = order === 'asc' ? 'desc' : 'asc';
		} else {
			sort = column;
			// Last login opens on the dormant end: that is the reason to sort by it at all.
			order = column === 'last_login' ? 'asc' : 'asc';
		}
		void refresh();
	}

	function setFilter(next: UserStatusFilter | null): void {
		statusFilter = next;
		void refresh();
	}

	function arrow(column: UserSort): string {
		return sort === column ? (order === 'asc' ? ' ↑' : ' ↓') : '';
	}

	// Written out one by one rather than assembled from a prefix: the i18n gate matches
	// literals, and a key it cannot see is a key it will call dead the day it stops being used.
	const filters = $derived([
		{ key: null, label: $_('admin.users.filterAll') },
		{ key: 'active' as const, label: $_('admin.users.filterActive') },
		{ key: 'disabled' as const, label: $_('admin.users.filterDisabled') },
		{ key: 'deleting' as const, label: $_('admin.users.filterDeleting') }
	]);

	// --- actions (10.F2) ---------------------------------------------------------------
	// A random temporary password, the same 8 alphanumerics the create form generates, shown
	// once in clear so the admin can read it out. Same generator, one definition.
	function randomPassword(): string {
		const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
		const bytes = new Uint32Array(8);
		crypto.getRandomValues(bytes);
		return Array.from(bytes, (b) => alphabet[b % alphabet.length]).join('');
	}

	async function act(run: () => Promise<unknown>): Promise<void> {
		error = null;
		notice = null;
		try {
			await run();
			await refresh();
		} catch (err) {
			// The server refuses an admin acting on themselves (10.B1). The buttons are hidden
			// for that row, so this only fires if the page is stale — say it plainly anyway.
			error =
				err instanceof ApiErr && err.code === 'cannot_target_self'
					? $_('admin.users.errorSelf')
					: $_('admin.users.errorGeneric');
		}
	}

	function doReset(user: AdminUser): void {
		if (!confirm($_('admin.users.confirmReset', { values: { username: user.username } }))) return;
		const password = randomPassword();
		void act(async () => {
			await resetUserPassword(user.id, password);
			notice = $_('admin.users.resetDone', { values: { username: user.username, password } });
		});
	}

	function doDelete(user: AdminUser): void {
		// The confirmation names the date the account actually dies, not just "are you sure":
		// the reversible window is the whole point of a deferred deletion, so it has to be on
		// the dialog that opens it.
		const preview = new Date(Date.now() + graceDays * 86_400_000).toLocaleDateString();
		const values = { username: user.username, date: preview };
		if (!confirm($_('admin.users.confirmDelete', { values }))) return;
		void act(() => markUserForDeletion(user.id));
	}

	function doRestore(user: AdminUser): void {
		if (!confirm($_('admin.users.confirmRestore', { values: { username: user.username } }))) return;
		void act(() => restoreUser(user.id));
	}

	function when(value: string | null): string {
		return value ? new Date(value).toLocaleDateString() : '—';
	}

	// 8 alphanumeric chars (A-Z a-z 0-9, no symbols), shown in clear so the admin
	// can read it out; they can also type their own temporary password instead.
	function generatePassword(): void {
		const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
		const bytes = new Uint32Array(8);
		crypto.getRandomValues(bytes);
		form.temp_password = Array.from(bytes, (b) => alphabet[b % alphabet.length]).join('');
	}

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
		// Checked first: an account on its way out is also inactive, and "disabled" would be
		// the less urgent half of the truth.
		if (user.deletion_marked_at) return $_('admin.users.statusDeleting');
		if (!user.is_active) return $_('admin.users.statusDisabled');
		if (user.must_change_password) return $_('admin.users.statusPending');
		return $_('admin.users.statusActive');
	}

	// The table printed the raw value, so a row read `super_user` — an identifier with an
	// underscore, shown where the form beside it uses proper labels. Same names in both places.
	const ROLE_LABEL: Record<string, string> = {
		user: 'admin.users.roleUser',
		super_user: 'admin.users.roleSuperUser',
		admin: 'admin.users.roleAdmin'
	};

	function roleLabel(role: string): string {
		// A role the frontend does not know about shows as-is rather than as an empty cell:
		// wrong is better than blank when the question is "what is this account".
		const key = ROLE_LABEL[role];
		return key ? $_(key) : role;
	}

	function lastLogin(user: AdminUser): string {
		return user.last_login_at
			? new Date(user.last_login_at).toLocaleString()
			: $_('admin.users.never');
	}

	const inputClass =
		'rounded border border-slate-300 bg-white px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-900';
	const fieldClass = 'flex flex-col gap-1 text-xs text-slate-500';
	const actionClass =
		'rounded border border-slate-300 px-2 py-1 hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800';
	const dangerClass =
		'rounded border border-red-300 px-2 py-1 text-red-600 hover:bg-red-50 dark:border-red-800 dark:text-red-400 dark:hover:bg-red-950/40';
</script>

<section class="space-y-8">
	<PageTitle title={$_('admin.users.title')} />

	<form onsubmit={submit} class="max-w-md space-y-3">
		<div class="grid grid-cols-2 gap-3">
			<label class={fieldClass}>
				{$_('admin.users.username')}
				<input class={inputClass} bind:value={form.username} required autocomplete="off" />
			</label>
			<label class={fieldClass}>
				{$_('admin.users.role')}
				<!--
					All three levels the API accepts (9.B8). Super-user was missing here, which
					made it unreachable: the role is chosen at creation and not changed afterwards
					(promoting an existing account is phase 10), so a level absent from this list
					was a level nobody could ever hold — and 9.F5, which restricts the manual
					scrape and the Debug entry to it, had no way to be exercised.
				-->
				<select class={inputClass} bind:value={form.role}>
					<option value="user">{$_('admin.users.roleUser')}</option>
					<option value="super_user">{$_('admin.users.roleSuperUser')}</option>
					<option value="admin">{$_('admin.users.roleAdmin')}</option>
				</select>
			</label>
		</div>
		<div class="grid grid-cols-2 gap-3">
			<label class={fieldClass}>
				{$_('admin.users.firstName')}
				<input class={inputClass} bind:value={form.first_name} required />
			</label>
			<label class={fieldClass}>
				{$_('admin.users.lastName')}
				<input class={inputClass} bind:value={form.last_name} required />
			</label>
		</div>
		<div class={fieldClass}>
			<span>{$_('admin.users.tempPassword')}</span>
			<div class="flex gap-2">
				<input
					class="{inputClass} flex-1"
					type="text"
					bind:value={form.temp_password}
					required
					minlength="8"
					autocomplete="off"
				/>
				<button
					type="button"
					onclick={generatePassword}
					class="rounded border border-slate-300 px-2 py-1 text-xs whitespace-nowrap hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800"
				>
					{$_('admin.users.generate')}
				</button>
			</div>
		</div>
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

	<div class="flex flex-wrap gap-2 text-xs">
		{#each filters as chip (chip.label)}
			<button
				type="button"
				onclick={() => setFilter(chip.key)}
				class="rounded-full border px-3 py-1 {statusFilter === chip.key
					? 'border-slate-800 bg-slate-800 text-white dark:border-slate-200 dark:bg-slate-200 dark:text-slate-900'
					: 'border-slate-300 hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800'}"
			>
				{chip.label}
			</button>
		{/each}
	</div>

	{#if loading}
		<p class="text-sm text-slate-500">{$_('common.loading')}</p>
	{:else}
		<table class="w-full text-left text-sm">
			<thead class="border-b border-slate-200 text-xs text-slate-500 dark:border-slate-800">
				<tr>
					<th class="cursor-pointer py-2 pr-4 select-none" onclick={() => sortBy('username')}
						>{$_('admin.users.username')}{arrow('username')}</th
					>
					<th class="py-2 pr-4">{$_('admin.users.colName')}</th>
					<th class="py-2 pr-4">{$_('admin.users.colRole')}</th>
					<th class="py-2 pr-4">{$_('admin.users.colStatus')}</th>
					<th class="cursor-pointer py-2 pr-4 select-none" onclick={() => sortBy('last_login')}
						>{$_('admin.users.colLastLogin')}{arrow('last_login')}</th
					>
					<th class="py-2 pr-4">{$_('admin.users.colMarkedAt')}</th>
					<th class="py-2 pr-4">{$_('admin.users.colDueAt')}</th>
					<th class="py-2 pr-4"></th>
				</tr>
			</thead>
			<tbody>
				{#each users as user (user.id)}
					<tr class="border-b border-slate-100 dark:border-slate-800/60">
						<td class="py-2 pr-4 font-medium">{user.username}</td>
						<td class="py-2 pr-4">{user.first_name} {user.last_name}</td>
						<td class="py-2 pr-4">{roleLabel(user.role)}</td>
						<td class="py-2 pr-4">{status(user)}</td>
						<td class="py-2 pr-4 text-slate-500">{lastLogin(user)}</td>
						<td class="py-2 pr-4 text-slate-500">{when(user.deletion_marked_at)}</td>
						<td
							class="py-2 pr-4 {user.deletion_due_at
								? 'text-red-600 dark:text-red-400'
								: 'text-slate-500'}">{when(user.deletion_due_at)}</td
						>
						<td class="py-2 pr-4">
							<!--
								Nothing at all on your own row, rather than disabled buttons: the API refuses
								it outright (10.B1), and a greyed-out control says "later, maybe" about
								something that is never going to be allowed.
							-->
							{#if user.id !== $auth.user?.id}
								<div class="flex flex-wrap gap-2 text-xs">
									<button type="button" class={actionClass} onclick={() => doReset(user)}
										>{$_('admin.users.actionReset')}</button
									>
									{#if user.deletion_marked_at}
										<button type="button" class={actionClass} onclick={() => doRestore(user)}
											>{$_('admin.users.actionRestore')}</button
										>
									{:else}
										<button
											type="button"
											class={actionClass}
											onclick={() => act(() => setUserActive(user.id, !user.is_active))}
											>{user.is_active
												? $_('admin.users.actionDisable')
												: $_('admin.users.actionEnable')}</button
										>
										<button type="button" class={dangerClass} onclick={() => doDelete(user)}
											>{$_('admin.users.actionDelete')}</button
										>
									{/if}
								</div>
							{/if}
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	{/if}
</section>
