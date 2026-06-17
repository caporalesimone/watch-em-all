import { writable } from 'svelte/store';

/** Product version reported by GET /api/health (baked from the git tag); shown in
 * the shell. Empty until the first fetch resolves. */
export const version = writable<string>('');
