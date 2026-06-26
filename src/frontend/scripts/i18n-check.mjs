// i18n consistency gate (4.B11). A dev/CI check — NOT shipped to production.
//
// English is the reference language (app-shell.md, English-first). This script
// compares the keys *used in the code* against the keys *defined in the English
// translation JSONs* (core + plugin namespaces) and fails on drift:
//
//   - MISSING: a key referenced by a literal `$_('a.b')` call that no en.json
//     defines (a typo, or a translation that was never added).
//   - DEAD:    a key defined in an en.json that never appears as an exact string
//     literal anywhere in the source (e.g. `changePassword.done`, orphaned after
//     the 0.3.4 auto-login).
//
// Keys assembled at runtime — e.g. `$_(`errors.${code}`)` — cannot be resolved
// statically; their prefixes live in i18n-check.config.json and are exempt from
// both checks. Everything else (including the Sidebar's `key: 'nav.systemLogs'`
// entries, passed indirectly through `$_(link.key)`) is a plain literal and is
// matched exactly, so a substring like `cache` never masks `cacheHint`.
//
// Locale parity (every locale carries exactly the English key set) is deliberately
// out of scope here and lands in phase 12 (12.T2 — Audit i18n: frontend), reusing
// the flatten/diff machinery below.
//
// Run by hand with `npm run i18n:check`; runs in CI on PRs (ci.yml) and on release
// tags (publish.yml), failing the pipeline on drift.

import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import process from 'node:process';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url)); // src/frontend/scripts
const FRONTEND_ROOT = join(HERE, '..'); // src/frontend
const SRC_ROOT = join(FRONTEND_ROOT, '..'); // src
const FE_SRC = join(FRONTEND_ROOT, 'src'); // src/frontend/src
const PLUGINS_ROOT = join(SRC_ROOT, 'plugins'); // src/plugins
const CONFIG_FILE = join(FRONTEND_ROOT, 'i18n-check.config.json');
const REPO_ROOT = join(SRC_ROOT, '..');

const SOURCE_EXTS = ['.svelte', '.ts', '.js', '.mjs'];
const SKIP_DIRS = new Set(['node_modules', '.svelte-kit', 'dist', 'build', 'generated', '.git']);
const PLUGIN_FOLDERS = ['scrapers', 'notifiers'];

// --- Pure helpers (exported for tests) -------------------------------------

/** Flatten a nested message dictionary to dotted leaf keys. */
export function flattenMessages(obj, prefix = '', out = {}) {
	for (const [k, v] of Object.entries(obj)) {
		const key = prefix ? `${prefix}.${k}` : k;
		if (v && typeof v === 'object' && !Array.isArray(v)) flattenMessages(v, key, out);
		else out[key] = v;
	}
	return out;
}

// `$_('a.b')` / `$_("a.b")` / `` $_(`a.b`) `` with a *pure literal* first arg.
// The content class forbids `$`, so interpolated template literals (the dynamic
// keys) do not match and fall through to the allow-list.
const CALLED_KEY_RE = /\$_\(\s*([`'"])([^`'"$]+)\1/g;
// Any single-line string literal. Used to mark a defined key as "referenced"
// even when it is passed indirectly (e.g. `key: 'nav.systemLogs'`).
const STRING_LITERAL_RE = /([`'"])([^`'"$\n]*)\1/g;

/** Keys referenced by a literal `$_(...)` call in one source file. */
export function extractCalledKeys(content) {
	const keys = new Set();
	for (const m of content.matchAll(CALLED_KEY_RE)) keys.add(m[2]);
	return keys;
}

/** Every single-line string literal in one source file (no interpolation). */
export function extractStringLiterals(content) {
	const lits = new Set();
	for (const m of content.matchAll(STRING_LITERAL_RE)) lits.add(m[2]);
	return lits;
}

/** True if `key` is covered by a runtime-assembled prefix (exempt from checks). */
export function underDynamicPrefix(key, prefixes) {
	return prefixes.some((p) => key.startsWith(p));
}

/**
 * Compare defined keys against usage. Returns { missing, dead } (sorted arrays).
 *  - defined:  Map(key -> json file it came from)
 *  - called:   Map(key -> Set(source files) that reference it via $_('lit'))
 *  - literals: Set(every string literal seen in the source)
 */
export function analyze({ defined, called, literals, dynamicPrefixes, ignoreKeys }) {
	const ignored = new Set(ignoreKeys);
	const exempt = (k) => ignored.has(k) || underDynamicPrefix(k, dynamicPrefixes);

	const missing = [...called.keys()]
		.filter((k) => !defined.has(k) && !exempt(k))
		.sort()
		.map((k) => ({ key: k, files: [...called.get(k)].sort() }));

	const dead = [...defined.keys()]
		.filter((k) => !literals.has(k) && !exempt(k))
		.sort()
		.map((k) => ({ key: k, file: defined.get(k) }));

	return { missing, dead };
}

// --- Filesystem collection -------------------------------------------------

/** Recursively list source files under `root`, skipping build/vendor dirs. */
function walkSources(root, out = []) {
	if (!existsSync(root)) return out;
	for (const name of readdirSync(root)) {
		const full = join(root, name);
		const st = statSync(full);
		if (st.isDirectory()) {
			if (SKIP_DIRS.has(name)) continue;
			walkSources(full, out);
		} else if (SOURCE_EXTS.some((ext) => name.endsWith(ext))) {
			out.push(full);
		}
	}
	return out;
}

/** The English reference JSONs: the core dictionary plus each plugin's en.json. */
export function collectEnglishFiles() {
	const files = [];
	const core = join(FE_SRC, 'i18n', 'en.json');
	if (existsSync(core)) files.push(core);
	for (const folder of PLUGIN_FOLDERS) {
		const base = join(PLUGINS_ROOT, folder);
		if (!existsSync(base)) continue;
		for (const name of readdirSync(base).sort()) {
			const en = join(base, name, 'frontend', 'i18n', 'en.json');
			if (existsSync(en)) files.push(en);
		}
	}
	return files;
}

/** All source roots scanned for key usage: the frontend app + plugin frontends. */
function collectSourceRoots() {
	const roots = [FE_SRC];
	for (const folder of PLUGIN_FOLDERS) {
		const base = join(PLUGINS_ROOT, folder);
		if (!existsSync(base)) continue;
		for (const name of readdirSync(base).sort()) {
			const fe = join(base, name, 'frontend');
			if (existsSync(fe)) roots.push(fe);
		}
	}
	return roots;
}

function rel(p) {
	return relative(REPO_ROOT, p).replaceAll('\\', '/');
}

// --- Runner ----------------------------------------------------------------

export function run() {
	const config = JSON.parse(readFileSync(CONFIG_FILE, 'utf8'));
	const dynamicPrefixes = config.dynamicPrefixes ?? [];
	const ignoreKeys = config.ignoreKeys ?? [];

	// Defined keys (English reference, core + plugins).
	const defined = new Map();
	const enFiles = collectEnglishFiles();
	for (const file of enFiles) {
		const flat = flattenMessages(JSON.parse(readFileSync(file, 'utf8')));
		for (const key of Object.keys(flat)) if (!defined.has(key)) defined.set(key, rel(file));
	}

	// Usage (literal $_() calls + every string literal) across all source.
	const called = new Map();
	const literals = new Set();
	const sourceFiles = collectSourceRoots().flatMap((r) => walkSources(r));
	for (const file of sourceFiles) {
		const content = readFileSync(file, 'utf8');
		for (const key of extractCalledKeys(content)) {
			if (!called.has(key)) called.set(key, new Set());
			called.get(key).add(rel(file));
		}
		for (const lit of extractStringLiterals(content)) literals.add(lit);
	}

	const { missing, dead } = analyze({ defined, called, literals, dynamicPrefixes, ignoreKeys });

	// Report.
	console.log('i18n consistency check (English reference)');
	console.log(`  reference JSONs : ${enFiles.length} (${enFiles.map(rel).join(', ')})`);
	console.log(`  defined keys    : ${defined.size}`);
	console.log(`  source files    : ${sourceFiles.length}`);
	console.log(
		`  dynamic prefixes: ${dynamicPrefixes.length ? dynamicPrefixes.join(' ') : '(none)'}`
	);
	console.log('');

	if (missing.length) {
		console.log(`✗ MISSING — used in $_() but not defined in any en.json (${missing.length}):`);
		for (const { key, files } of missing) console.log(`    ${key}  ←  ${files.join(', ')}`);
		console.log('');
	}
	if (dead.length) {
		console.log(`✗ DEAD — defined in en.json but never used in code (${dead.length}):`);
		for (const { key, file } of dead) console.log(`    ${key}  (${file})`);
		console.log('');
	}

	const problems = missing.length + dead.length;
	if (problems === 0) {
		console.log('✓ i18n is consistent — no missing or dead keys.');
		return 0;
	}
	console.log(
		`FAIL: ${problems} problem(s) — ${missing.length} missing, ${dead.length} dead. ` +
			'Add the missing keys to en.json, remove the dead ones, or list a genuinely ' +
			'dynamic key in i18n-check.config.json.'
	);
	return 1;
}

// Run only when invoked directly (not when imported by tests).
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
	process.exit(run());
}
