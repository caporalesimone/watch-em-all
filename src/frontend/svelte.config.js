import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** SPA (CSR only): adapter-static with an index.html fallback so all routes are
 * resolved client-side (app-shell.md). The built bundle is later baked into the
 * web image and served by FastAPI. */
const config = {
	preprocess: vitePreprocess(),
	kit: {
		adapter: adapter({ fallback: 'index.html' })
	}
};

export default config;
