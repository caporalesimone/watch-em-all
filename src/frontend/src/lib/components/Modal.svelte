<!--
	The one popup (10.T2). Everything that appears over the page goes through here: confirmations,
	the JSON inspector on the logs page, the schedule editor, the notification reader.

	The point Simone made when asking for it is that behaviour should live in the parent, so this
	component owns *all* of it — the overlay, closing on Escape, closing on a click outside the
	panel, locking the page behind it, moving focus in on open and giving it back on close, and
	the aria wiring. A derived popup supplies content and buttons and inherits the rest; if the
	way a popup closes ever has to change, it changes once.

	Deliberately not a native <dialog>: `showModal()` is the browser's own focus trap and top-layer
	handling, which is genuinely nice, but its backdrop cannot be transitioned or themed the way
	the rest of this app is, and Safari's support arrived late enough that the fallback would have
	to exist anyway. One implementation beats one plus a fallback.
-->
<script lang="ts">
	import type { Snippet } from 'svelte';

	let {
		open = $bindable(false),
		title,
		icon = null,
		size = 'md',
		closeLabel,
		onclose,
		children,
		actions
	}: {
		open?: boolean;
		title: string;
		/** A single emoji shown beside the title. Decorative: it is aria-hidden. */
		icon?: string | null;
		size?: 'sm' | 'md' | 'lg';
		closeLabel: string;
		onclose?: () => void;
		children: Snippet;
		actions?: Snippet;
	} = $props();

	const WIDTH = { sm: 'max-w-sm', md: 'max-w-lg', lg: 'max-w-2xl' } as const;

	let panel = $state<HTMLDivElement | null>(null);
	let restoreTo: HTMLElement | null = null;

	export function close(): void {
		open = false;
		onclose?.();
	}

	$effect(() => {
		if (!open) return;
		// Remember who had focus so it goes back there — a popup that swallows the caret leaves
		// keyboard users hunting for their place in the page.
		restoreTo = document.activeElement as HTMLElement | null;
		const previousOverflow = document.body.style.overflow;
		document.body.style.overflow = 'hidden'; // the page behind must not scroll away
		panel?.focus();

		function onKey(event: KeyboardEvent): void {
			if (event.key === 'Escape') {
				event.preventDefault();
				close();
				return;
			}
			if (event.key !== 'Tab' || !panel) return;
			// Focus trap: Tab off either end wraps inside the panel instead of walking off into
			// the page underneath, which is unreachable anyway while this is open.
			const focusable = panel.querySelectorAll<HTMLElement>(
				'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
			);
			if (focusable.length === 0) return;
			const first = focusable[0];
			const last = focusable[focusable.length - 1];
			if (event.shiftKey && document.activeElement === first) {
				event.preventDefault();
				last.focus();
			} else if (!event.shiftKey && document.activeElement === last) {
				event.preventDefault();
				first.focus();
			}
		}

		window.addEventListener('keydown', onKey);
		return () => {
			window.removeEventListener('keydown', onKey);
			document.body.style.overflow = previousOverflow;
			restoreTo?.focus();
		};
	});
</script>

{#if open}
	<!-- The backdrop closes on click. It carries no role and no key handler: Escape is bound on
	     the window above, which is where a keyboard user expects it, so a11y linting has nothing
	     to ask of a div that exists to be a grey rectangle. -->
	<div
		class="fixed inset-0 z-[90] flex items-center justify-center bg-slate-900/50 p-4 backdrop-blur-[2px]"
		onclick={(e) => {
			if (e.target === e.currentTarget) close();
		}}
		role="presentation"
	>
		<div
			bind:this={panel}
			tabindex="-1"
			role="dialog"
			aria-modal="true"
			aria-label={title}
			class="flex max-h-[85vh] w-full {WIDTH[
				size
			]} flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-2xl outline-none dark:border-slate-700 dark:bg-slate-900"
		>
			<header
				class="flex items-start gap-3 border-b border-slate-200 px-5 py-4 dark:border-slate-800"
			>
				{#if icon}
					<span class="text-2xl leading-none" aria-hidden="true">{icon}</span>
				{/if}
				<h2 class="flex-1 text-base font-semibold">{title}</h2>
				<button
					onclick={close}
					aria-label={closeLabel}
					class="-mt-1 rounded px-2 text-xl leading-none text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800"
				>
					×
				</button>
			</header>

			<div class="flex-1 overflow-y-auto px-5 py-4">
				{@render children()}
			</div>

			<footer
				class="flex flex-wrap justify-end gap-2 border-t border-slate-200 px-5 py-3 dark:border-slate-800"
			>
				{#if actions}
					{@render actions()}
				{:else}
					<button
						onclick={close}
						class="rounded border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800"
					>
						{closeLabel}
					</button>
				{/if}
			</footer>
		</div>
	</div>
{/if}
