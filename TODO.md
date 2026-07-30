# TODO

Running list of issues / polish noted by Simone, to address in a future pass.
New items get appended over time.

## Phase 9 code review (2026-07-30)

A read of the phase-9 code — plugin backend, parser, sanitiser, core catalog/alerts, worker, web
routers, the three frontend components — looking for dead branches, simplifiable logic and logic
errors.

Split into three groups, because "mechanical" can mean two different things: *no decision to take*,
and *no change in behaviour*. Group A had both, group B only the first, group C neither. The three
that changed what the user sees were C1, C2 and C3; none was covered by a test, for the same reason
— the tests went through `run_for_user`, while C2 lived on the *add* path and C3 needed a warm
cache. **C1 is still open**, in group C, because it is a decision and not a repair.

**Groups A and B are done** (2026-07-30, one commit each) — see `git log --grep='(C'`.

- **A**: C4, C11, C12, C13, C16, C17, C18, C21. Two did not survive contact unchanged, and the
  commits say why: C17's field had readers after all (the tests that proved it was parsed), and
  C21's obvious fix — drop the narrowed field — would have traded one duplicate reference for
  three casts, so the *other* reference went instead.
- **B**: C2, C3, C6, each with the test that was missing. Every one was checked against the
  unfixed code first: C2 landed a 9,90 product at 0,00 with a Free tag, C3's counters read (2, 0)
  where they should read (1, 1), C6's counter stayed at zero. C2 needed a fixture change to be
  *able* to fail — both priceless cards of the real listing turn out to be free, so reading their
  detail pages and discarding those reads produced the same catalog. C3 also sharpened PROD-R8 in
  [product.md](docs/4-capabilities/contracts/product.md): a page of many products carries the
  timestamp **per page**, not per run.

**Group C is open.**

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
