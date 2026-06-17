// svelte-i18n setup (FE-13). V1 ships en (the complete fallback) plus it; the
// selector is not exposed (English-first, app-shell.md). New strings are added
// to en.json first.
import { addMessages, init, locale, waitLocale } from 'svelte-i18n';

import en from '../../i18n/en.json';
import it from '../../i18n/it.json';

let started = false;

export function setupI18n(initialLocale = 'en'): Promise<void> {
	if (!started) {
		addMessages('en', en);
		addMessages('it', it);
		init({ fallbackLocale: 'en', initialLocale });
		started = true;
	}
	return waitLocale();
}

export { locale };
