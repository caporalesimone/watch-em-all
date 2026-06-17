import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [tailwindcss(), sveltekit()],
	server: {
		// Dev proxy so the SPA talks to the FastAPI app without CORS.
		proxy: {
			'/api': 'http://localhost:8080'
		}
	}
});
