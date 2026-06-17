// svelte-i18n setup (FE-13). V1 ships en (the complete fallback) plus it; the
// selector is not exposed (English-first, app-shell.md). New strings are added
// to en.json first.
//
// addMessages + init run at MODULE LOAD (import side effect): the locale must be
// set before any component formats a message ($_), otherwise svelte-i18n throws
// "Cannot format a message without first setting the initial locale". Since the
// dictionaries are added synchronously, the locale is ready immediately.
import { addMessages, init, locale, waitLocale } from 'svelte-i18n';

import en from '../../i18n/en.json';
import it from '../../i18n/it.json';

addMessages('en', en);
addMessages('it', it);
init({ fallbackLocale: 'en', initialLocale: 'en' });

/** Await the active locale's dictionary (resolves immediately for bundled ones). */
export function setupI18n(): Promise<void> {
	return waitLocale();
}

export { locale };
