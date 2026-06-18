import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';

// Plugin frontends live in src/plugins (outside this SvelteKit project root); let
// the dev server read them so the generated registry can import via `$plugins`
// (the alias is declared in svelte.config.js). 2.F1 / build-system.md.
const repoRoot = fileURLToPath(new URL('../..', import.meta.url));

export default defineConfig({
	plugins: [tailwindcss(), sveltekit()],
	server: {
		fs: { allow: [repoRoot] },
		// Dev proxy so the SPA talks to the FastAPI app without CORS.
		proxy: {
			'/api': 'http://localhost:8080'
		}
	}
});
