// Toast store (phase 7 design-system): transient, non-blocking outcome messages shown by the
// single top-center Toaster (mounted once at the app-shell root). Any component pushes a toast;
// it auto-dismisses after a few seconds or on click. Shared across notifiers and reusable anywhere.
import { writable } from 'svelte/store';

export type ToastVariant = 'success' | 'error' | 'info';

export interface Toast {
	id: number;
	variant: ToastVariant;
	message: string;
}

export const toasts = writable<Toast[]>([]);

let nextId = 1;
const TTL_MS = 5000;

export function pushToast(message: string, variant: ToastVariant = 'info'): void {
	const id = nextId++;
	toasts.update((list) => [...list, { id, variant, message }]);
	setTimeout(() => dismissToast(id), TTL_MS);
}

export function dismissToast(id: number): void {
	toasts.update((list) => list.filter((t) => t.id !== id));
}
