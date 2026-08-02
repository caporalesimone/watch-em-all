<script lang="ts">
	import { onMount } from 'svelte';
	import { _ } from 'svelte-i18n';

	import {
		ApiErr,
		createUser,
		getSettings,
		listUsers,
		markUserForDeletion,
		purgeUser,
		resetUserPassword,
		restoreUser,
		setUserActive,
		type AdminUser,
		type NewUser,
		type UserSort,
		type UserStatusFilter
	} from '$lib/api/client';
	import PageTitle from '$lib/components/PageTitle.svelte';
	import { confirmDialog } from '$lib/stores/confirm';
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
		role: 'user'
	};
	let form = $state<NewUser>({ ...empty });

	// The username is an email address (10.B23). This check is deliberately **weaker** than the
	// server's: its job is to catch a typo before the round trip, and erring on the permissive
	// side means the only thing it can ever do is let through something the server refuses —
	// never the reverse. The authority is the regex in `src/core/identity.py`, and duplicating
	// *that* here is exactly the two-implementations-of-one-rule trap 9.F8 had to undo.
	const EMAIL_SHAPE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
	const addressLooksWrong = $derived(form.username.length > 0 && !EMAIL_SHAPE.test(form.username));

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
			order = 'asc';
		}
		void refresh();
	}

	// Every column, in the order the table shows them (10.F28). Written out as literals so the
	// i18n gate can see each key, and defined once so the header cannot disagree with the body
	// about which columns exist.
	const columns = $derived([
		{ key: 'username' as const, label: $_('admin.users.username') },
		{ key: 'name' as const, label: $_('admin.users.colName') },
		{ key: 'role' as const, label: $_('admin.users.colRole') },
		{ key: 'status' as const, label: $_('admin.users.colStatus') },
		{ key: 'last_login' as const, label: $_('admin.users.colLastLogin') },
		{ key: 'marked_at' as const, label: $_('admin.users.colMarkedAt') },
		{ key: 'due_at' as const, label: $_('admin.users.colDueAt') }
	]);

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
	// Errors this page can actually explain, rather than one generic sentence for everything.
	// The two email ones are new with 10.B24 and are the reason a create or a reset can now
	// fail for a reason that has nothing to do with the account.
	function explain(err: unknown): string {
		if (!(err instanceof ApiErr)) return $_('admin.users.errorGeneric');
		if (err.code === 'cannot_target_self') return $_('admin.users.errorSelf');
		if (err.code === 'username_taken') return $_('admin.users.errorTaken');
		if (err.code === 'email_channel_unavailable') return $_('admin.users.errorNoEmail');
		if (err.code === 'password_email_failed') return $_('admin.users.errorMailFailed');
		if (err.code === 'purge_failed') return $_('admin.users.errorPurgeFailed');
		return $_('admin.users.errorGeneric');
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
			error = explain(err);
		}
	}

	async function doReset(user: AdminUser): Promise<void> {
		// The confirmation names the consequences, because since 10.B24 there are three and none
		// of them is visible from the button: a new password is generated, it is mailed to the
		// account, and every session that person has open ends. The admin never sees it.
		const ok = await confirmDialog({
			title: $_('admin.users.actionReset'),
			message: $_('admin.users.confirmReset', { values: { username: user.username } }),
			highlight: [user.username],
			confirmLabel: $_('admin.users.actionReset'),
			danger: true
		});
		if (!ok) return;
		void act(async () => {
			await resetUserPassword(user.id);
			notice = $_('admin.users.resetDone', { values: { username: user.username } });
		});
	}

	async function doDelete(user: AdminUser): Promise<void> {
		// The confirmation names the date the account actually dies, not just "are you sure":
		// the reversible window is the whole point of a deferred deletion, so it has to be on
		// the dialog that opens it.
		const preview = new Date(Date.now() + graceDays * 86_400_000).toLocaleDateString();
		const values = { username: user.username, date: preview };
		const ok = await confirmDialog({
			title: $_('admin.users.actionDelete'),
			message: $_('admin.users.confirmDelete', { values }),
			highlight: [values.username, values.date],
			confirmLabel: $_('admin.users.actionDelete'),
			danger: true
		});
		if (!ok) return;
		void act(() => markUserForDeletion(user.id));
	}

	async function doPurge(user: AdminUser): Promise<void> {
		// The one dialog on this page that describes something with no way back, so it says all
		// three parts out loud: the deadline on the row is being waived, the data goes with the
		// account, and the person is told by email. "Are you sure?" would be the wrong question —
		// the admin is sure, what they may not know is what exactly is about to happen.
		const due = when(user.deletion_due_at);
		const ok = await confirmDialog({
			title: $_('admin.users.actionPurge'),
			message: $_('admin.users.confirmPurge', { values: { username: user.username, date: due } }),
			// The date only if there is one: `when()` answers an em dash for a missing value, and
			// emphasising that would pick out every dash in the sentence instead.
			highlight: user.deletion_due_at ? [user.username, due] : [user.username],
			confirmLabel: $_('admin.users.actionPurge'),
			danger: true
		});
		if (!ok) return;
		void act(async () => {
			await purgeUser(user.id);
			notice = $_('admin.users.purgeDone', { values: { username: user.username } });
		});
	}

	async function doRestore(user: AdminUser): Promise<void> {
		const ok = await confirmDialog({
			title: $_('admin.users.actionRestore'),
			message: $_('admin.users.confirmRestore', { values: { username: user.username } }),
			highlight: [user.username],
			confirmLabel: $_('admin.users.actionRestore')
		});
		if (!ok) return;
		void act(() => restoreUser(user.id));
	}

	async function doToggleActive(user: AdminUser): Promise<void> {
		// Asked for, in both directions, because neither is only a flag. Disabling ends every
		// session that person has open and emails them about it; enabling lets somebody back in
		// who was deliberately shut out. Both are worth a beat between the click and the effect —
		// and the two buttons sit where a deletion used to, on rows a mis-click can reach.
		const disabling = user.is_active;
		const action = disabling ? 'admin.users.actionDisable' : 'admin.users.actionEnable';
		const ok = await confirmDialog({
			title: $_(action),
			message: disabling
				? $_('admin.users.confirmDisable', { values: { username: user.username } })
				: $_('admin.users.confirmEnable', { values: { username: user.username } }),
			highlight: [user.username],
			confirmLabel: $_(action),
			danger: disabling
		});
		if (!ok) return;
		void act(() => setUserActive(user.id, !user.is_active));
	}

	function when(value: string | null): string {
		return value ? new Date(value).toLocaleDateString() : '—';
	}

	async function submit(event: Event): Promise<void> {
		event.preventDefault();
		error = null;
		notice = null;
		submitting = true;
		try {
			const created = await createUser(form);
			// Says where the password went, because that is the only copy of it: nothing on this
			// page will ever show it again, and the admin has nothing to write down (10.B24).
			notice = $_('admin.users.created', { values: { username: created.username } });
			form = { ...empty };
			await refresh();
		} catch (err) {
			error = explain(err);
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
				<input
					class={inputClass}
					type="email"
					bind:value={form.username}
					required
					autocomplete="off"
					placeholder="name@example.com"
				/>
				{#if addressLooksWrong}
					<span class="text-amber-600 dark:text-amber-400">{$_('admin.users.notAnAddress')}</span>
				{/if}
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
		<!-- No password field since 10.B24. Said out loud rather than silently absent: an admin
		     who used to type one here needs to know it is now generated and mailed, and that
		     they will not see it. -->
		<p class="text-xs text-slate-500 dark:text-slate-400">{$_('admin.users.passwordIsMailed')}</p>
		<button
			type="submit"
			disabled={submitting || addressLooksWrong}
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
					{#each columns as column (column.key)}
						<th class="py-2 pr-4">
							<!-- A real button, not a clickable <th>: sorting a table is an action, and a
							     keyboard has to be able to reach it. -->
							<button
								type="button"
								class="cursor-pointer font-normal select-none hover:text-slate-700 dark:hover:text-slate-300"
								onclick={() => sortBy(column.key)}
							>
								{column.label}{arrow(column.key)}
							</button>
						</th>
					{/each}
					<th class="py-2 pr-4"></th>
				</tr>
			</thead>
			<tbody>
				{#each users as user (user.id)}
					<!--
						An account that cannot sign in reads dimmer than one that can (10.F28). Faded,
						not hidden and not struck through: it is still a row to act on — the buttons on
						it keep their normal weight — but the eye should find the working accounts
						without reading the Status column one line at a time. It covers accounts on
						their way out too, which are inactive by definition; their deletion date stays
						red, because that is the one thing on the row still worth noticing.
					-->
					<tr
						class="border-b border-slate-100 dark:border-slate-800/60 {user.is_active
							? ''
							: 'text-slate-400 dark:text-slate-500'}"
					>
						<td class="py-2 pr-4 font-medium">{user.username}</td>
						<td class="py-2 pr-4">{user.first_name} {user.last_name}</td>
						<td class="py-2 pr-4">{roleLabel(user.role)}</td>
						<td class="py-2 pr-4">{status(user)}</td>
						<!-- Secondary on an active row, inherited on a faded one: `text-slate-500` is
						     *darker* than the row's `text-slate-400`, so keeping it would make the
						     least important cells the strongest thing on a disabled line. -->
						<td class="py-2 pr-4 {user.is_active ? 'text-slate-500' : ''}">{lastLogin(user)}</td>
						<td class="py-2 pr-4 {user.is_active ? 'text-slate-500' : ''}"
							>{when(user.deletion_marked_at)}</td
						>
						<td
							class="py-2 pr-4 {user.deletion_due_at
								? 'text-red-600 dark:text-red-400'
								: user.is_active
									? 'text-slate-500'
									: ''}">{when(user.deletion_due_at)}</td
						>
						<td class="py-2 pr-4">
							<!--
								Nothing at all on your own row, rather than disabled buttons: the API refuses
								it outright (10.B1), and a greyed-out control says "later, maybe" about
								something that is never going to be allowed.
							-->
							{#if user.id !== $auth.user?.id}
								<div class="flex flex-wrap gap-2 text-xs">
									<!--
										A row on its way out gets its own pair of actions. Resetting the password
										of an account nobody can sign into was the previous occupant of this
										space and did nothing at all: the mail would go out, the new password
										would work on a login the deletion gate refuses anyway. What belongs
										here is the other end of the same decision — finish it now (10.F20).
									-->
									{#if user.deletion_marked_at}
										<button type="button" class={actionClass} onclick={() => doRestore(user)}
											>{$_('admin.users.actionRestore')}</button
										>
										<button type="button" class={dangerClass} onclick={() => doPurge(user)}
											>{$_('admin.users.actionPurge')}</button
										>
									{:else}
										<button type="button" class={actionClass} onclick={() => doReset(user)}
											>{$_('admin.users.actionReset')}</button
										>
										<button type="button" class={actionClass} onclick={() => doToggleActive(user)}
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
