import { writable } from 'svelte/store';

import type { AdminError } from '$lib/api/client';

/** Admin-facing errors/warnings from GET /api/admin/errors (admin-only). Empty → no
 * banner. Populated by the layout only for an admin in the shell. */
export const adminErrors = writable<AdminError[]>([]);
