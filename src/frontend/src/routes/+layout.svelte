<script lang="ts">
	import '../app.css';

	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { _ } from 'svelte-i18n';

	import Header from '$lib/components/Header.svelte';
	import Sidebar from '$lib/components/Sidebar.svelte';
	import { setupI18n } from '$lib/i18n';
	import { auth, bootstrap } from '$lib/stores/auth';
	import { theme } from '$lib/stores/theme';

	let { children } = $props();
	let ready = $state(false);

	onMount(async () => {
		theme.init();
		await setupI18n();
		await bootstrap();
		ready = true;
	});

	// Route guard (app-shell boot sequence): anon → /login; pending password change
	// → /change-password; authed elsewhere → keep out of the auth pages.
	$effect(() => {
		if (!ready) return;
		const state = $auth;
		const path = $page.url.pathname;
		if (state.status === 'anon') {
			if (path !== '/login') void goto('/login');
		} else if (state.status === 'authed') {
			if (state.user?.must_change_password) {
				if (path !== '/change-password') void goto('/change-password');
			} else if (path === '/login' || path === '/change-password') {
				void goto('/');
			}
		}
	});

	const showShell = $derived(
		ready && $auth.status === 'authed' && !$auth.user?.must_change_password
	);
</script>

{#if !ready}
	<div class="flex h-full items-center justify-center text-sm text-slate-500">
		{$_('common.loading')}
	</div>
{:else if showShell}
	<div class="flex h-full">
		<Sidebar />
		<div class="flex flex-1 flex-col">
			<Header />
			<main class="flex-1 overflow-auto p-6">{@render children()}</main>
		</div>
	</div>
{:else}
	<main class="flex h-full items-center justify-center p-6">{@render children()}</main>
{/if}
