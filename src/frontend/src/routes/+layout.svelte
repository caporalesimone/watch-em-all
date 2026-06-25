<script lang="ts">
	import '../app.css';

	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { _ } from 'svelte-i18n';

	import { getHealth, getSchemaDrift } from '$lib/api/client';
	import SchemaDriftBanner from '$lib/components/SchemaDriftBanner.svelte';
	import Sidebar from '$lib/components/Sidebar.svelte';
	import { setupI18n } from '$lib/i18n';
	import { auth, bootstrap } from '$lib/stores/auth';
	import { loadPlugins, resetPlugins } from '$lib/stores/plugins';
	import { schemaDrift } from '$lib/stores/schemaDrift';
	import { theme } from '$lib/stores/theme';
	import { version } from '$lib/stores/version';

	let { children } = $props();
	let ready = $state(false);
	let pluginsLoaded = $state(false);
	let driftLoaded = $state(false);

	onMount(async () => {
		theme.init();
		await setupI18n();
		await bootstrap();
		// Non-blocking: fill the version shown in the shell.
		void getHealth()
			.then((h) => version.set(h.version))
			.catch(() => {});
		ready = true;
	});

	// Route guard (app-shell boot sequence): anon → /login; pending password change
	// → /change-password; authed elsewhere → keep out of the auth pages.
	$effect(() => {
		if (!ready) return;
		const state = $auth;
		const path = $page.url.pathname;
		if (state.status === 'anon') {
			if (path !== '/login') void goto('/login', { replaceState: true });
		} else if (state.status === 'authed') {
			if (state.user?.must_change_password) {
				if (path !== '/change-password') void goto('/change-password', { replaceState: true });
			} else if (state.user?.role === 'admin') {
				// Admin lives in the admin area; no user dashboard/scrapers (roles don't overlap).
				if (path === '/login' || path === '/change-password' || path === '/')
					void goto('/admin/users', { replaceState: true });
			} else {
				// Standard user: keep out of the auth pages and the admin area.
				if (path === '/login' || path === '/change-password' || path.startsWith('/admin'))
					void goto('/', { replaceState: true });
			}
		}
	});

	// Load the plugin list once the user is authed; clear it on sign-out (FDISC-R2).
	$effect(() => {
		if (!ready) return;
		const state = $auth;
		if (
			state.status === 'authed' &&
			!state.user?.must_change_password &&
			state.user?.role !== 'admin'
		) {
			if (!pluginsLoaded) {
				pluginsLoaded = true;
				void loadPlugins();
			}
		} else if (state.status === 'anon' && pluginsLoaded) {
			pluginsLoaded = false;
			resetPlugins();
		}
	});

	// Schema drift is an ADMIN-ONLY diagnostic (served by an admin endpoint, not the
	// public health probe): fetch it once when an admin is in the shell, and clear it
	// otherwise so it never lingers for a normal user.
	$effect(() => {
		if (!ready) return;
		const state = $auth;
		const isAdmin =
			state.status === 'authed' &&
			state.user?.role === 'admin' &&
			!state.user?.must_change_password;
		if (isAdmin && !driftLoaded) {
			driftLoaded = true;
			void getSchemaDrift()
				.then((d) => schemaDrift.set(d))
				.catch(() => {});
		} else if (!isAdmin && driftLoaded) {
			driftLoaded = false;
			schemaDrift.set([]);
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
		<main class="flex-1 overflow-auto p-6">{@render children()}</main>
	</div>
{:else}
	<main class="flex h-full items-center justify-center p-6">{@render children()}</main>
{/if}

<!-- Dev-only; self-hides unless GET /api/health reports schema drift (4.F0). -->
<SchemaDriftBanner />
