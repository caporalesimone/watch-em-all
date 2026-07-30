# TODO

Running list of issues / polish noted by Simone, to address in a future pass.
New items get appended over time.

## Phase 9 code review (2026-07-30)

A read of the phase-9 code — plugin backend, parser, sanitiser, core catalog/alerts, worker, web
routers, the three frontend components — looking for dead branches, simplifiable logic and logic
errors. Nothing here is fixed yet.

Split into three groups, because "mechanical" can mean two different things: *no decision to take*,
and *no change in behaviour*. Group A has both, group B only the first, group C neither. **C1, C2 and
C3 change what the user sees**, and none of the three is covered by a test, for the same reason: the
tests go through `run_for_user`, while C1/C2 live on the *add* path and C3 needs a warm cache.

### Group A — mechanical: no decision, no change in behaviour

Safe as one commit. The fix is stated with each finding because there is only one.

| ID | Description, filename |
|---|---|
| **C4** | **Dead code**: `_scrape_products` (~23 lines) and the `_ScrapeOutcome` dataclass are called by nobody — leftovers of the `run_for_user` reordering in `9.B4`. *Fix: delete both.* — [backend/\_\_init\_\_.py](src/plugins/scrapers/dragon_store/backend/__init__.py) lines 104 and 608 |
| **C11** | **The watch counters are kept twice**: the add path writes them by hand (`products_included = 1`, and `last_scanned_at` twice — in `_record_scan` and again at the end) while `run_for_user` uses `_record_scan`. Two routes for the same three fields. *Fix: the add path calls `_record_scan` too.* — [backend/\_\_init\_\_.py](src/plugins/scrapers/dragon_store/backend/__init__.py) |
| **C12** | **Misleading comment**: `addWatch`'s describes the pre-`9.X6b` world ("scrapes the product there and then… could be submitted twice"); the POST now answers in milliseconds and the block is the server's. *Fix: rewrite the comment.* — [PluginRoot.svelte](src/plugins/scrapers/dragon_store/frontend/PluginRoot.svelte) |
| **C13** | **Stale delisted count**: `delistedTotal` refreshes on mount and after a cleanup, never after `load()`. If a scrape delists while the page is open (or during the initial retry loop), the button stays *"Remove delisted (0)"* and disabled with delisted rows on screen. *Fix: refresh it from `load()`.* — [catalog/+page.svelte](src/frontend/src/routes/catalog/+page.svelte) |
| **C16** | **Docstring contradicts the code**: `classify_url` says *"Judged on shape alone, host included"* but reads only `urlsplit(url).path` — the host is never checked. *Fix: say that.* — [backend/parser.py](src/plugins/scrapers/dragon_store/backend/parser.py) |
| **C17** | **Dead data**: `ParsedCategory.page_size` is parsed off the header and never consumed. *Fix: drop the field and its assignment.* — [backend/parser.py](src/plugins/scrapers/dragon_store/backend/parser.py) |
| **C18** | **The privileged-role set is hand-copied into two components** (`['super_user','admin']`), a third copy of the backend's `_SUPER_ROLES`; the next restricted page will make a fourth. *Fix: one exported helper, imported by both.* — [PluginRoot.svelte](src/plugins/scrapers/dragon_store/frontend/PluginRoot.svelte) + [Sidebar.svelte](src/frontend/src/lib/components/Sidebar.svelte) |
| **C21** | **Redundant field**: `_Drainer.plugin` is the same object as `_Drainer.manifest_and_plugin.plugin`. *Fix: drop the field, read it off the loaded plugin.* — [web/jobs.py](src/web/jobs.py) |

### Group B — mechanical edit, but behaviour changes: needs a test

The change is small and obvious; what is missing is the coverage that would have caught it.

| ID | Description, filename |
|---|---|
| **C2** | **On the add path the work of `9.B2b` is done and discarded.** `_resolve_unpriced` is handed a **throwaway** dict built inline; it writes the detail-page-resolved products into it, then `products = outcome.products` uses the **unpriced** versions. The HTTP requests (with their politeness wait) go out and are wasted. The same code in `run_for_user` is correct — which is why no test sees it. *Fix: pass a real dict and deliver its values; two lines, plus the missing test on the add path.* — [backend/\_\_init\_\_.py](src/plugins/scrapers/dragon_store/backend/__init__.py) `_resolve_watch` |
| **C3** | **Category products violate PROD-R8.** `_fetch_category_page` discards `response.fetched_at` and `_scrape_category` passes `None` to `_card_to_product`, so `scraped_at = now()` even off the cache. Twice harmful: `last_seen_at` lies for up to 12 h (the defect `9.X4` fixed for single products) and `_update_statistics` counts every cached delivery as `observations` instead of `cache_hits` — two `9.B6b` counters wrong by construction on the phase's main input. *Fix: carry `fetched_at` through the walk — plumbing, but it touches `ParsedCategory` and a signature.* — [backend/\_\_init\_\_.py](src/plugins/scrapers/dragon_store/backend/__init__.py) + [core/catalog.py](src/core/catalog.py) |
| **C6** | **`parse_failures_total` counts half the failures**: bumped in `_fetch_category_page`, never in the `DragonStoreParseError`/`DragonStoreSoftError` branches of `_scrape_one`. The health statistic is asymmetric between listings and product pages. *Fix: bump it on the parse-error branch. The soft-error branch is a judgement — a site error page is not a parse failure.* — [backend/\_\_init\_\_.py](src/plugins/scrapers/dragon_store/backend/__init__.py) `_scrape_one` |

### Group C — not mechanical: a decision is inside

Each of these has more than one defensible answer, so it is Simone's call before code.

| ID | Description, filename |
|---|---|
| **C1** | **Cancelling a category add throws away everything it had read.** `_JobCancelled` propagates out of `_scrape_category` **before** `context.upsert_catalog(...)`, so the local product dict dies with the exception. The code comment, the message shown to the user and the phase doc all claim the opposite ("what was already read stays in your catalog"). *Decision: write what was read before re-raising, or change the promise. Two different products, not two implementations.* — [backend/\_\_init\_\_.py](src/plugins/scrapers/dragon_store/backend/__init__.py) `_resolve_watch` / `_scrape_category` |
| **C5** | **A cancelled job records no counters**: `_record_scan` is never reached, so the row reads "Not read yet" and the outcome panel announces "The **0** products already read stay in your catalog". *Depends on C1: what to record follows from what is kept.* — [backend/\_\_init\_\_.py](src/plugins/scrapers/dragon_store/backend/__init__.py) `_resolve_watch` |
| **C7** | **`removed_at` is written and read by nobody**: not in `_SORT_COLUMNS`, not exposed on `CatalogItem`, and `9.B9` fires once off the baseline's `removed` flag. Both justifications in its comment ("the cleanups sort on it, the notification needs it") are untrue today. *Decision: expose it and sort on it, or admit in the comment that it is for a later phase.* — [core/catalog.py](src/core/catalog.py) `update_catalog` / [routers/catalog.py](src/web/routers/catalog.py) |
| **C8** | **`_to_product` and `_card_to_product` are near-identical** (~40 lines: sanitise, tags, preorder, breadcrumb, `_resolve_price`, `Product` construction) and already diverging — which is exactly the crack C3 slipped through. *Decision: a real refactor, including how to keep the differences (`extra`, where availability comes from).* — [backend/\_\_init\_\_.py](src/plugins/scrapers/dragon_store/backend/__init__.py) |
| **C9** | **`_cancel_requested` opens a fresh session every 250 ms** for the whole politeness wait: ~900 sessions/queries to read one boolean over a 21-page category. *Not a substitution: the fresh session exists so it can see another session's commit. Reusing one means deciding how to make it re-read.* — [backend/\_\_init\_\_.py](src/plugins/scrapers/dragon_store/backend/__init__.py) `_cancellable_sleep` |
| **C10** | **A plugin commits the worker's session.** The `context.db.commit()` inside the walk is deliberate on the web path (the page polls that row), but in a scheduled run it closes the worker's unit of work as a side effect. *Decision: architectural — who owns the transaction.* — [backend/\_\_init\_\_.py](src/plugins/scrapers/dragon_store/backend/__init__.py) `_scrape_category` |
| **C14** | **The single-product delete confirmation does not state `9.B7`'s accepted consequence**: a product still watched comes back on the next run. Only the empty-catalog confirmation says it. *Decision: the page does not know whether that product is watched, so the wording has to be honest without that.* — [catalog/+page.svelte](src/frontend/src/routes/catalog/+page.svelte) + [i18n/en.json](src/frontend/src/i18n/en.json) |
| **C15** | **`removeWatch` swallows errors** (nothing is shown if the DELETE fails) and does not clear `outcome`: the outcome panel stays pinned to a watch that no longer exists. *Clearing `outcome` is trivial; the error message needs deciding — which one, and whether it wants a new key.* — [PluginRoot.svelte](src/plugins/scrapers/dragon_store/frontend/PluginRoot.svelte) |
| **C19** | **A delisted product shows *Difference* `0%`** in the email and the in-app history: `price_previous == price_current` by construction, so a percentage is printed on a row nobody can buy. *The payload does not say a product is delisted: suppressing the column means adding that information or inferring it from the tag.* — [alerts/[id]/+page.svelte](src/frontend/src/routes/alerts/[id]/+page.svelte) + [notifiers/email](src/plugins/notifiers/email/backend/__init__.py) |
| **C20** | **`progress_done = progress_total or 1` at the end of a job**: a category interrupted on page 3 of 21 records 21 pages read. *Decision: what `progress_done` should mean on an interrupted job — the pages really read, or leave it.* — [backend/\_\_init\_\_.py](src/plugins/scrapers/dragon_store/backend/__init__.py) `_resolve_watch` |
| **C22** | **`fmt` and `fmtInterval` are two near-identical duration formatters** (they differ only in how they render seconds) — pre-existing duplication, now sitting next to a third date format. *Decision: merging them means choosing one rendering; the two call sites differ today on purpose.* — [PluginRoot.svelte](src/plugins/scrapers/dragon_store/frontend/PluginRoot.svelte) |

## Off topic

- **Two Claude Code skills: start-of-work and end-of-work.** Create a `/start-work` skill that opens a
  phase/PR (branch, dated status header, empty CHANGELOG placeholder, version bookkeeping) and an
  `/end-work` skill that closes it (finalize the CHANGELOG entry, tick the checklist, the tag +
  GitHub-release steps, image/version sanity check). They'd encode the repeatable versioning/tagging
  ritual — one tag per phase, no `v` prefix, `WEA_VERSION` in `.env`, version baked from `git describe`
  — so it isn't re-derived by hand each time. See [`docs/env-variables.md`](docs/env-variables.md) and
  the version notes in [ci](docs-ita/infrastructure/ci.md) for what the skills should automate.
