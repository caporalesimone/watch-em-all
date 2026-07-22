<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { _ } from 'svelte-i18n';

	import * as api from '$lib/api/client';
	import PageTitle from '$lib/components/PageTitle.svelte';
	import { auth, forceAnon } from '$lib/stores/auth';
	import { theme } from '$lib/stores/theme';

	let current = $state('');
	let next = $state('');
	let confirm = $state('');
	let error = $state('');
	let busy = $state(false);

	const field =
		'w-full rounded border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900';

	// --- Alert cadence (6.F2) ---
	// weekdays: 0=Mon … 6=Sun; [] = off. The backend canonicalises the time; we bind
	// "HH:MM" to the <input type="time">.
	const WEEKDAYS: { value: number; key: string }[] = [
		{ value: 0, key: 'weekdays.mon' },
		{ value: 1, key: 'weekdays.tue' },
		{ value: 2, key: 'weekdays.wed' },
		{ value: 3, key: 'weekdays.thu' },
		{ value: 4, key: 'weekdays.fri' },
		{ value: 5, key: 'weekdays.sat' },
		{ value: 6, key: 'weekdays.sun' }
	];

	let cadenceDays = $state<number[]>([]);
	let cadenceTime = $state('09:00');
	let cadenceLoaded = $state(false);
	let cadenceBusy = $state(false);
	let cadenceNotice = $state('');

	onMount(async () => {
		try {
			const s = await api.getAlertSchedule();
			cadenceDays = [...s.weekdays].sort((a, b) => a - b);
			if (s.scheduled_time) cadenceTime = s.scheduled_time.slice(0, 5);
		} catch {
			/* leave the defaults; the Save button still works */
		} finally {
			cadenceLoaded = true;
		}
	});

	function toggleDay(value: number): void {
		cadenceDays = cadenceDays.includes(value)
			? cadenceDays.filter((d) => d !== value)
			: [...cadenceDays, value].sort((a, b) => a - b);
	}

	async function saveCadence(): Promise<void> {
		cadenceBusy = true;
		cadenceNotice = '';
		try {
			const res = await api.setAlertSchedule({
				scheduled_time: cadenceTime,
				weekdays: cadenceDays
			});
			cadenceDays = [...res.weekdays].sort((a, b) => a - b);
			if (res.scheduled_time) cadenceTime = res.scheduled_time.slice(0, 5);
			// ALERT-R3: flipping the on/off state clears or reseeds the monitoring baselines.
			if (res.baseline_effect === 'cleared') cadenceNotice = $_('profile.cadenceResetCleared');
			else if (res.baseline_effect === 'reseeded')
				cadenceNotice = $_('profile.cadenceResetReseeded');
			else cadenceNotice = $_('common.saved');
		} finally {
			cadenceBusy = false;
		}
	}

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

	<section class="space-y-3 text-sm">
		<h2 class="font-medium">{$_('profile.cadence')}</h2>
		<p class="text-slate-500 dark:text-slate-400">{$_('profile.cadenceHint')}</p>

		<div class="space-y-1">
			<span class="block text-slate-500 dark:text-slate-400">{$_('profile.cadenceDays')}</span>
			<div class="flex flex-wrap gap-1">
				{#each WEEKDAYS as d (d.value)}
					<button
						type="button"
						aria-pressed={cadenceDays.includes(d.value)}
						onclick={() => toggleDay(d.value)}
						class="rounded border px-2.5 py-1 text-xs {cadenceDays.includes(d.value)
							? 'border-indigo-500 bg-indigo-600 text-white'
							: 'border-slate-300 text-slate-600 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800'}"
					>
						{$_(d.key)}
					</button>
				{/each}
			</div>
		</div>

		<div class="flex items-center gap-2">
			<label for="cadence-time" class="text-slate-500 dark:text-slate-400"
				>{$_('profile.cadenceTime')}</label
			>
			<input
				id="cadence-time"
				type="time"
				bind:value={cadenceTime}
				class="rounded border border-slate-300 bg-white px-2 py-1 dark:border-slate-700 dark:bg-slate-900"
			/>
		</div>

		{#if cadenceDays.length === 0}
			<p class="text-amber-600 dark:text-amber-400">{$_('profile.cadenceOff')}</p>
		{/if}

		<div class="flex items-center gap-3">
			<button
				type="button"
				onclick={saveCadence}
				disabled={cadenceBusy || !cadenceLoaded}
				class="rounded bg-indigo-600 px-4 py-2 font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
			>
				{$_('common.save')}
			</button>
			{#if cadenceNotice}<span class="text-xs text-slate-500">{cadenceNotice}</span>{/if}
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
