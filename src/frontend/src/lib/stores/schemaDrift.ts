import { writable } from 'svelte/store';

import type { SchemaDriftItem } from '$lib/api/client';

/** Schema drift reported by GET /api/health (4.B0). The backend exposes it only
 * when WEA_SCHEMA_DRIFT_ALERT is on; an empty list means no banner (4.F0). */
export const schemaDrift = writable<SchemaDriftItem[]>([]);
