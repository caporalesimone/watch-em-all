import { browser } from '$app/environment';
import { writable } from 'svelte/store';

export type Theme = 'light' | 'dark';

function read(): Theme {
	if (!browser) return 'dark';
	return localStorage.getItem('theme') === 'light' ? 'light' : 'dark';
}

function createTheme() {
	let current: Theme = read();
	const { subscribe, set } = writable<Theme>(current);

	function apply(next: Theme): void {
		current = next;
		if (browser) {
			localStorage.setItem('theme', next);
			document.documentElement.classList.toggle('dark', next === 'dark');
		}
		set(next);
	}

	return {
		subscribe,
		/** Re-apply the persisted theme (the inline script already set the class). */
		init: () => apply(current),
		toggle: () => apply(current === 'dark' ? 'light' : 'dark')
	};
}

export const theme = createTheme();
