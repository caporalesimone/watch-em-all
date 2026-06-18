import { defineConfig } from 'vitest/config';

// Scoped to the plain-Node build tooling (the build:plugins generator). It does
// not load the SvelteKit plugin: there are no component tests here (phase 2 UI is
// verified by build + manual checks, per the agreed test approach).
export default defineConfig({
	test: {
		include: ['scripts/**/*.test.mjs'],
		environment: 'node'
	}
});
