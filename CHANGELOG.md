# Changelog

All notable changes to this project are documented in this file.

The project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Every PR carries exactly one version bump and one entry here (1 MVP = 1 PR = 1 version). Release tags are **not** per-PR: the owner creates a plain SemVer `x.y.z` tag (no `v` prefix) **by hand** when a release is wanted, and pushing it triggers the publish workflow (versioned images on GHCR); the GitHub release is then created on that tag (no assets — the deploy kit lives in the repo). Intermediate per-PR versions live only in this file.

Each entry is **short** and reads as a user-facing story: first a **bullet list of what changed for you** (additions, removals and changes together, light on jargon), then a brief **_under the hood_** paragraph on the architectural/technical changes. Older entries predate this style and are left as they are.

## [0.9.0] - Unreleased

**Phase 9 — Dragon Store, complete: paste a category URL and dozens of products flow into your catalog on every run (with de-duplication and the site's own exclusions); delisted products grey out on their own and clear with a click. A product's price history now belongs to the product, so it outlives your catalog and you inherit it when you start watching.**

> **This version recreates the database.** Pre-1.0 the schema changes freely and is not migrated: the price history is re-keyed, and two tables are new. Existing data is not carried over.

### New

- **Paste a category, watch everything in it.** A Dragon Store listing URL is now an input in its own right: one line pasted once, and every run reads the whole category — all its pages — and brings the products into your catalog. A category of a thousand products costs 21 requests, which at the ten seconds the site asks between them is about four minutes; the page shows you which page it is on while it works, and you can stop it — stopping discards what it had read, because half a category is not what you asked for, and the pages already fetched stay cached so a later run gets them free.
- **Dented items stay out unless you ask for them.** Dragon Store sells damaged-box copies as separate listings. They are **excluded by default** from a category, and a toggle — offered when you paste the URL, changeable afterwards on the row — lets them in for that category alone. A dented product you add *on purpose*, as a single URL, always comes in and says so on its row: the title arrives with the label cleaned off, so nothing else would tell you.
- **The page knows what you pasted.** As you paste, it says whether the URL is a product or a category (and tells you plainly when it is neither), which is how it knows whether to offer you the dented toggle at all.
- **Adding tells you what came in.** Since there is no preview any more, the add reports afterwards: how many products went into your catalog, how many dented listings were skipped, and a link to go and see them. Every input then keeps that line on its row — what it last gave you, and when it was last read — so a filter doing its job looks different from a filter quietly eating your catalogue.
- **Delisted products, and clearing them.** A product the store stops offering is marked delisted, with the date. Three cleanups now sit above the catalog: remove the delisted ones, delete individual rows (behind a *Delete mode*, so it is never a mis-click next to the add-to-cart checkbox), or empty the catalog. Each says what goes with it, in numbers rather than warnings: **how many of the rows are in one of your carts** and will be taken out of them, and — for a single product — **which of your inputs still delivers it**, so you are told "it still comes from *Il Richiamo di Cthulhu*, the next run will bring it back" instead of being left to guess. Its **price history stays**: that belongs to the product, so it is waiting for you if you add it again. Each cleanup tells you how many rows went, and emptying leaves your watches alone, so the next run refills whatever you still watch.
- **Be told when something in your cart is delisted.** A new cart alert: *A product is no longer listed*. It fires **once**, on the run that notices, and never again — and a product that is already gone stops generating price and stock alerts, since its last known price is not news any more.
- **A product's price history is the product's, not yours.** Add something today and you already have its past: the prices it has had while anybody else was watching it, including from before you arrived. Stop watching it, or remove it from your catalog, and that history is not destroyed — it stays for whoever watches it next. One person watching is enough to keep it growing for everybody. Nothing here is ever deleted automatically; tidying up history no one references any more will be an administrator's tool in a later version.

### Removed

- **The dry-run preview is gone.** Pasting a URL used to offer a *Preview* that scraped the page and showed what it found without saving it; you then pressed *Add*, which scraped the same page again. Since 0.8.1 adding a URL already stores the product, so the preview was asking a site that requests 10 seconds between requests to serve the same page twice for a single intention — and a preview that saves nothing looked exactly like an add that does. Now there is one button.

### Fixed

- **The notification said a price had fallen when it had risen.** An email digest reported `Was €39.92 · Now €49.90 · Discount -0%` on a product that had just come *off* a sale and gone up in price. The column was showing the discount against the product's list price — a different quantity from the two columns beside it, and legitimately zero here — with a minus sign written into the template. It is now a **Difference** column: the signed change between the two prices in the row, `+25%` in red when the price rises, negative in green when it falls, an em dash when there is nothing to compare against. ([#37](https://github.com/caporalesimone/watch-em-all/issues/37))
- **A delisted product no longer reports `0%`.** In the digest and in the in-app history, a product that had left the store showed *Difference* `0%` — its last two prices are identical by definition, so the column read "the price held steady" about something you can no longer buy. It now shows an em dash, in the email and on the page alike, which cannot drift apart any more because both are shown the same number.
- **Cancelling an add says what it did.** It used to promise that "the products already read stay in your catalog", which was never true — nothing was stored. It now says plainly that nothing was added, and that the input stays in your list for the next scheduled run.
- **A removal that fails now tells you.** Removing an input from the Dragon Store list reported nothing when it went wrong: the row stayed and you were left to work out why. And after removing one, the panel describing what had just been added kept talking about an input that no longer existed.
- **The health endpoint finally says whether the worker is running**, and an administrator is told when it is not. `worker_heartbeat_age_s` had been `null` since the first version — a placeholder nobody filled — while the worker *was* beating, into a file only its own container could read: `docker compose ps` said healthy, the API said nothing, and the two never met. Now it reports the seconds since the worker last spoke, and the admin diagnostics tell apart the three cases that need different actions: it never started, it stopped (with how long ago, and that no scrape or notification is going out meanwhile), or it stopped **itself** and why. Not something you have to go and read container logs for.
- **"Include dented items" was unreadable**, which is fair — *dented* is a literal translation of the label Dragon Store puts on cheaper copies with a damaged box, and it explains nothing on its own. The toggle now reads **"Also include damaged-box copies"** and says what they are: a second, cheaper entry the store lists for the same item, labelled *Ammaccato*, skipped by default and brought in from the next scan, keeping that label as a tag so you can tell them apart. The counts and the warning on a single product say the same thing in the same words.
- **You can actually create a super-user.** The new level was accepted by the API but missing from the role dropdown when creating an account — and since a role is chosen at creation and never changed afterwards (promoting an existing account is a later version), it was a level nobody could hold. Which also meant the restriction it exists for — *Scrape now* and the **Debug** entry being visible only to a super-user or an admin — could not be exercised at all. The user table also printed the raw value, so a row read `super_user`, an identifier with an underscore, next to a form that used proper names; both places now say **Super-user**.
- **A database that does not match the version now says so, on every page.** Pull new containers onto an older database — which before 1.0 is an ordinary thing to do, since the schema is not migrated — and you used to get a scattering of *Internal server error* from whichever page happened to touch the wrong table first, with the real reason in a startup log nobody re-reads. Now the application starts and every page answers with **one screen** naming the tables that disagree, the version running, and what to do about it (recreate the database, or go back to the previous version — nothing has been written). The worker suspends its scheduled work for the same reason and keeps its heartbeat, so it does not look like a second, separate fault; `/api/health` stays reachable for monitoring.

### Changed

- **Scrape now belongs to a new *super-user* level.** A manual scrape is the quickest way to send a store more requests than it asks for, so it is no longer everyone's: alongside `user` and `admin` there is now `super_user`, and only they (and the admin) see the button and the **Debug** entry — which used to be shown to everyone. Not greyed out: absent. The level is chosen when the account is created.
- **The catalog remembers more about each product.** Every product now quietly accumulates its own numbers — how many times it was actually read, how often the data came off a cached page, how many price and stock changes, its lowest and highest price and when — and every scraper keeps lifetime totals of its own runs, requests, pages, rate limits and gate hits. Nothing shows them yet; they are being collected so that when they are shown, there is something real to look at.
- **The log says when the application starts and stops.** Both the web and the worker now record their own startup and shutdown, with the running version. Only the worker's startup used to appear, by accident of how its logger was named, and nothing at all announced a shutdown — so on a day with one scheduled scrape, a container restart and a quiet afternoon looked exactly alike. The web's boot checks (feature flags, schema drift) become visible on the same page, alongside the worker's. ([#35](https://github.com/caporalesimone/watch-em-all/issues/35))
- **Administrators land on the system logs.** Signing in as an administrator used to open the user list. It now opens **System logs**, on the reasoning that the first thing you want to know is whether anything is failing right now.
- **The system log is easier to watch.** Live tailing now lets you pick its rate (1s / 5s / 10s), and the green dot flashes on every check — so a quiet log looks different from a stuck one. Rows carry a **Date** column, not just a time. Refresh and rows-per-page grey out while tailing, since neither means anything then, and picking a level filter no longer resizes the search box. Rows per page are now 50 / 100 / 200.
- **Price charts say when the product was last read.** A **Last seen** timestamp sits above the chart. A flat line used to be ambiguous — stable price, or nobody looking? — which is exactly what the Dragon Store outage would have looked like. It is the moment the **site** answered: a scrape served from the cache does not move it, and a caption underneath says so.

_Under the hood:_ the phase's two structural decisions. **The watch row is the job**: `POST /watches` commits the row and answers in milliseconds, and the scrape happens afterwards, drained by a per-scraper worker holding the same run lock as a scheduled run. Before, the wait sat inside the request with everything describing it living in the page — a reload wiped the spinner but not the scrape, which finished and wrote invisibly, and the user, seeing nothing, added the same URL again; the duplicate check was a `SELECT` two minutes before its `INSERT`, so it is now a `UNIQUE (user_id, url)`. Job state (status, progress counted in requests, a cooperative cancel flag) lives on that row, which is what lets a reload find the operation again, and what lets the next scheduled run finish a job a restart interrupted. **And a delivery knows whether it is complete**: a category page that could not be read downgrades the whole run to the non-delisting write path (CATSVC-R2b), because "we could not read page 7" is not "those products are gone" — the confusion that emptied a catalogue in 0.8.1. A category is **one row**, not one per product: a product can arrive from several categories at once, so there is no foreign key back to the watch and what the UI needs is kept on the watch as counters instead. Categories are walked first because a card and a detail page share an `external_id`, so five single watches covered by one category go from 77 seconds to 22. The URL grammar stays in the plugin and is exposed as `GET /classify` rather than copied into TypeScript; the dented filter reads the sanitiser's tag instead of searching the title a second time (the sanitiser strips the label, so a second search would find nothing), and that match is now anchored to the ends of the title; the delisting alert works because the baseline keeps delisted members with a `removed` flag — excluding them, as it did, left the transition with nothing to be a transition from. Three defects surfaced on the way: SQLite silently ignores `ON DELETE CASCADE` unless `PRAGMA foreign_keys` is on, so the test database disagreed with production about what deleting a product does (switching it on immediately exposed six tests writing orphan rows); `scrape_run.products_excluded` had existed since phase 4 with nothing ever writing it, so a run over a category of 39 reported 38 found and left the missing one unexplained; and a category had no name at all, because no delivered product lives at the watch's own URL — it now takes the site's breadcrumb.

_Under the hood:_ the phase's own code review found ten things worth a decision, and they turned into four structural changes plus their consequences. **Price history is keyed on the product**, `(plugin_id, external_id)`, with no foreign key into the per-user catalog: it used to hang off a catalog row, so two users watching the same product kept two chains of the same public fact — duplicated, and free to *diverge*, because an entry is written by comparing against the previous entry of its own chain and a chain that starts later opens on a "first price" that was never the product's first. The counters stay per user, which is now asked as a separate question (CATSVC-R4b): `price_changes` compares against what *that user's row* held, since asking the shared chain would answer for whoever was delivered first and tell every other watcher that nothing had moved. **`product_sources`** records which inputs delivered each product, many-to-many, described rather than joined — a watch lives in the plugin's own schema, so there is nothing for a core foreign key to point at — which is what lets a confirmation name what will bring a product back; a single foreign key was refused in 9.B4 precisely because a product can arrive from two categories at once, and that is the argument *for* the many-to-many. **`ScraperPlugin.build_product`** is now `final` and owns everything identical across scrapers (SCR-R18): identity through the template-method, `discount_pct` left to the core, `scraped_at` from the site's answer with the clock only as a fallback, one `extra` predicate, `availability` read as schema.org. The same assembly had been written by hand in three places across two plugins and had already drifted — a discarded `fetched_at`, and two different predicates for filtering `extra`, so an empty description survived one path and was dropped by the other; `tp_scraper`'s copy carried `scraped_at=now()`, the one line PROD-R8 forbids and exactly what a third scraper would have copied. **`context.jobs`** (CTX-R13) takes a transaction away from plugins rather than adding a feature: publishing progress means committing while the work runs, and on a scheduled run the session a plugin holds is the *worker's*, mid-`run_for_user`, with a half-filled `scrape_user_log` in it — that half-row became durable, and a process dying before the worker finished left it behind for ever with a NULL status. The core keeps that book on short-lived sessions of its own, the same pattern as the scrape cache, which also removes the ~900 sessions a 21-page walk used to open to read one boolean. Two smaller notes: a finished job **keeps** its progress row, because "read 2 of 21 pages" is the record a walk stopped early has to keep showing, so a stale cancellation is cleared when the next one begins; and the Difference rule moved into the core payload, paying off the debt 9.F8 declared and could not pay — the objection was that the payload is stored, and the reset that this version already needs leaves nothing stored to be missing it. CTX-R9 now also states the rule the cache always followed and never wrote down: anything read from the site is cached even when the result is thrown away, because it is a courtesy to the site rather than a feature of one scrape.

_Under the hood:_ the schema-drift guard (4.B0) grew the half it was missing and a way to act on what it finds ([schema-compatibility](docs/4-capabilities/core/schema-compatibility.md), INC-R1..R6). It reported columns the **model** wanted and the database lacked — the phase-3 case, where `create_all` cannot add a column to a table that already exists — and was blind to the mirror image: a column the **database still requires** (`NOT NULL`, no default) that the model no longer writes, which rejects every `INSERT`. That is precisely the half a *new* version produces: 0.9.0 on a 0.8.0 database reported the missing `price_history` columns and said nothing about the leftover columns that break adding a watch. A leftover the database does not require is still not reported, deliberately — nullable, or with a default, it sits there unread, and everything reported is now treated as an incompatibility rather than a remark. Acting on it: the web installs a middleware ahead of every route, reading a state the lifespan fills before the first request is served, so there is no window in which a mismatched database is reachable; `/api/` answers `503` JSON, everything else the page, and `/api/health` is the single exception. Refusing to start was the other candidate and is worse for whoever has to fix it — a container that exits leaves only `docker logs` to read and, under a restart policy, exits in a loop. The page is self-contained (inline CSS, no asset, no i18n lookup) because it has to render when the database is unusable, and it escapes the table and column names it prints: they come from a database this process does not control.

_Under the hood:_ the test suite now runs across cores (`pytest-xdist`, `-n auto`). It was the CI's entire critical path — 247 s of a 280 s job, with lint and typecheck costing 12 s between them — while every other job finished inside 50 s. Nothing had to be restructured: each worker is its own process, so the module-level engine and the in-memory SQLite were already isolated, the plugin tests' mock servers bind port 0, and no fixture is session-scoped. It did surface one real defect: `test_cart_series_empty_cart` built its own session from the global factory and only ever passed because an earlier test in the same process had initialised the engine. Locally the suite goes from 3m41s to ~25s. The test client's HTTP transport also moved from `httpx` to `httpx2` ([#36](https://github.com/caporalesimone/watch-em-all/issues/36)) — where Starlette 1.3 looks for it, and where that library is maintained now. It was the only warning the suite emitted, and the fallback that produced it will eventually become an import error, which would take the collection of every test file down with it rather than one test. The workflows' `actions/checkout`, `actions/setup-node` and `actions/setup-python` also moved to their current majors, in the publish workflow as well as in CI: they were two to three majors behind and still running on Node 20, which GitHub already forces onto Node 24 while annotating every run.

## [0.8.1] - 2026-07-26

**Fix — Dragon Store stopped being readable: the site added an anti-bot gate, and we discovered we had been crawling seven times faster than its `robots.txt` asks. Both sides are fixed, plus the worse bug this uncovered: a failed scrape used to wipe your catalogue.**

### Fixed

- **Dragon Store products are readable again.** Since 25 July the site answered the first request of every session with a "Verifica accesso / Security Check" page instead of the product, which reached the logs as the thoroughly misleading `no JSON-LD Product`. Watch 'Em All now recognises that page and gets past it once per run, the same way the page's own checkbox does.
- **A failed scrape no longer empties your catalogue.** This was the serious one. When every product of a run failed to load, the run reported "nothing found" and everything that scraper had given you was marked **delisted**: carts flagged unhealthy, alerts silenced, prices gone. It repaired itself on the next good run, but meanwhile your catalogue looked wiped. A run that could not read the site now changes nothing.
- **We were going too fast.** Dragon Store's `robots.txt` asks for 10 seconds between requests; we were leaving 1.5, and retries went out after half a second — almost certainly what earned the `429 Too Many Requests` the site had started returning. Watch 'Em All now reads `robots.txt` and obeys it.

### Changed

- **Adding a URL now fills your catalogue immediately.** Pasting a product URL already triggered a scrape, but only to fetch the title for display — a price appeared only after the next run, or after pressing *Scrape now*. That same scrape now stores the product: one intention, one round of requests to the site.
- **Politer defaults.** Minimum delay between two requests to the same site: **11 seconds** (was 1.5). Cached page half-life: **12 hours** (was 1). Both remain per-scraper admin settings; an existing configuration is left untouched, so check *Admin → Sources* if yours was set by hand.
- **Logs you can debug from.** A run now states what it read from `robots.txt`, which `Crawl-delay` it parsed and which interval won, when it hit the gate and got through, and when it gave up. Anything that stops a product from being read is logged as an **error**, not a warning.
- **We stop misidentifying ourselves.** The User-Agent sent to every site was the literal `watch-em-all/0.3` — frozen since phase 3, five versions out of date. It is now built from the running build's version, so it can't drift again.

_Under the hood:_ the fix lives in the core client, not in the scraper — a rule a plugin has to remember to apply is a rule a plugin will eventually forget. A new `src/core/robots.py` (pure, stdlib) turns a fetched `robots.txt` into a policy; `HttpClient` fetches it once per origin per run and enforces it (CTX-R10): `Disallow` via `urllib.robotparser` — a blocked URL raises `RobotsDenied` without opening a socket — and `Crawl-delay` as a **floor**, `max(politeness_delay_ms, Crawl-delay)`, so neither our config nor the site's request can be undercut. `Crawl-delay` is not in RFC 9309 (Google ignores it); we honour it anyway, and parse it ourselves so fractional values survive. Retrieval failures follow §2.3.1: `4xx` allows everything, `5xx` disallows the whole origin. `robots.txt` is exempt from the delay it declares and does not start the politeness clock, so a single-page scrape stays instant. The client also keeps a **cookie jar for the whole run** (the cleared session was being thrown away on every page, which is why the gate kept reappearing) and gained `forget(url)` (CTX-R11), since a `200` is not proof of a useful body and an interstitial must not be replayed from cache for twelve hours. Politeness is re-applied before **every** attempt, retries included. On the catalogue side `update_catalog` was split: `upsert_products` writes without the delisting sweep, `update_catalog` is that plus the sweep (CATSVC-R2b), and the choice belongs to whoever knows whether a delivery is complete — the scraper now tracks unread watches and downgrades to the non-delisting path, aborting the run outright on a rate limit rather than making it worse. Dragon Store's parser classifies the body into interstitial / soft error (their error pages carry the real status inside a `200`) / genuinely unparseable, and the paths that build their own context — adding a watch, the dry run — go through the shared `build_http_client` instead of a bare client that quietly ignored the admin config.

## [0.8.0] - 2026-07-23

**Phase 8 — price-history charts: the price/availability series the system has been accumulating since phase 3 become visible — per product and per cart, with availability gaps shown (not interpolated).**

### New

- **Price-history charts.** The prices Watch 'Em All has been quietly recording since phase 3 are now something you can **look at**. A product's chart is a **step line** of its discounted price with an **explicit gap** over every stretch it was out of stock — the line never pretends there was a price when there wasn't. A cart's chart shows the **total over time** of its current members. Both come with **Week / Month / All** selectors and a hover tooltip (date, price, and “out of stock” on a gap), read cleanly in light and dark, and animate smoothly when you switch range.
- **A Price history page, plus in-context shortcuts.** There's a new **Price history** entry in the sidebar (Product | Cart toggle + a picker). You can also jump straight there: a **chart icon** on each row of the Product Picker opens that product's chart, and a **View price chart** action on a cart's page opens the cart's total. The links carry the selection, so the page opens on the right series.

_Under the hood:_ the read side of `price_history` is served **ready to plot** — the SPA never aggregates (HISTC-R4). A small `src/core/price_history.py` turns the append-only table into stepped series: `GET /api/products/{id}/history?range=` for a product (with the last change before the window carried in, clamped to the window start, so the line starts at the right price) and `GET /api/carts/{id}/history?range=` for a cart (the stepped sum of the current members, each counted only while available; the current composition is projected onto the past — no membership history). Both are per-user (a product/cart you don't own is a 404). The one chart component is built on **Chart.js** (canvas, explicitly registered to stay lean; animations left on for smooth transitions); the availability gap is rendered by breaking the line, never interpolating. No new data is collected and history is never pruned — this phase only reads and draws.

## [0.7.0] - 2026-07-23

**Phase 7 — email notifications: your alert digests stop living only inside the app and start arriving in your inbox. This closes the product's minimum value chain (the 0.1).**

### New

- **Email notifications.** Your alert digests can now leave the app and arrive by **email**. Each user adds their address in the **Profile → Notification channels** section, presses **Send test** to prove it works, and turns the channel **on** — from then on, whenever a scrape produces changes, the digest also lands in the inbox, formatted (per-cart sections with the events, old → new price, where each product is from, totals and threshold) with a plain-text fallback. An administrator configures the shared SMTP server once on the new **Admin → Notifiers** page.
- **Notification channels, with the in-app one among them.** The Profile now lists every delivery **channel** with a clear status (available / needs your details / active). The **in-app** history you already had is now shown as a channel too — always on for you (you can't switch it off), so nothing is lost even if email fails. Each configurable channel has its own form, an on/off switch and a **Test** button.
- **Two-level configuration.** The **admin** sets the shared parts of a channel (for email: SMTP host, port, credentials, sender); each **user** sets their personal part (their address) and enables it for themselves. Until the admin has configured a channel it shows as "not available"; secrets (like the SMTP password) are **write-only** — saved but never shown back, only a "saved" indicator.
- **Admin channel switch.** An administrator can turn a whole channel **off for everyone** from the Notifiers page (e.g. if a mail server breaks) — personal settings are kept, and the channel simply disappears for users until it's turned back on. This applies to the in-app channel too (the only way it can be switched off).
- **Delivery outcomes in the history.** Opening a notification now shows, per channel, whether it was **delivered**, is still **pending**, **failed** (with the reason) or was skipped — so a broken email is visible without hiding anything: the in-app history stays the source of truth.
- **Debug menu (dev).** A temporary **Debug** entry at the bottom of the sidebar links to the development tools (Mailpit inbox, API docs, database browser); it will be removed before v1.

_Under the hood:_ a new **NotifierPlugin** contract (`send` / `send_test` / declarative `ConfigField` admin & user schemas) turns the phase-2 marker into a real family; the core renders one dynamic form from the schema, filters saved keys to the declaring side (a user can't inject an admin key), keeps secrets write-only, and merges admin+user config for delivery. Delivery is **decoupled from the scrape** (the design decided in phase 6): when the alert engine writes a digest it records one `alert_delivery` row per active channel — the **in-app** channel is local, so it's marked delivered inline; network channels start `pending` and a **separate periodic worker step drains them** (send with the plugin's own short retry/backoff, then `delivered` / `failed`), so a slow or failing SMTP never blocks a run. It's best-effort: a failed send isn't retried forever — the next digest carries the new state. The **in-app channel is now a first-class notifier** (`in_app`) governed by the admin switch, which unifies the dispatch and lets the inbox be hidden globally if an admin disables it. The **Email** plugin uses only the standard library (`smtplib` + STARTTLS), renders the digest as inline-CSS HTML + text, and raises a readable error after its retries. New tables: `alert_delivery`, `notifier_admin_config`, `notifier_user_config`. For local testing, a **Mailpit** service is added to the dev compose (SMTP on 1025, inbox UI on 8025); production uses a real SMTP server.

## [0.6.0] - 2026-07-23

**Phase 6 — in-app alerts: on each cart you pick which changes matter, and right after every scrape the system drops a single readable digest into the Alert History — event-driven, with nothing to schedule.**

### New

- **In-app alerts.** Watch 'Em All now tells you when something worth buying happens — **automatically, right after prices update**. On each **cart** you pick which changes matter — a product goes **on sale** / its discount ends / goes **out of stock** / is **back in stock**, the **whole cart goes on sale**, or the **savings threshold is reached**. There's **nothing to schedule**: whenever a scrape updates your catalog (automatic, on-demand, or the test generator), the system compares each cart against the last time it looked and, if anything changed, drops a single aggregated **digest** into a new **Alerts** section — what changed, old → new price, where it's from, and the cart's totals and threshold. The sidebar shows an **unread** badge (kept live) and you can **select and delete** notifications from the history. It's all **in-app** for now (email and other channels come later), and every notification is kept in the history until you remove it. Enabling alerts on a cart **starts monitoring from now**, so you're told about future changes, not past ones.

- **The catalog's "add to cart" picker now guides your choice.** When you select products and pick a target cart, **single-store carts that don't match your selection are greyed out** — a single-store cart only accepts products from its own store, and if your selection spans more than one store all single-store carts are disabled (cross-store carts always stay available). A short note explains why, so an incompatible add is prevented up front instead of failing on submit.

### Changed

- **TP Scraper (dev tool) can now stage changes and "simulate a scrape".** On the TP Scraper page you can **edit a product's price or availability** inline and then press **Simulate scrape** to push every product's current values into the catalog at once — the same way a real scrape would. It makes the new alerts easy to try end to end: build a cart, enable alerts, drop a price, simulate a scrape, and watch the digest appear right away.

### Fixed

- **Carts no longer vanish on a full page reload.** Reloading the browser on the **Carts** page left it empty; you had to click **Carts** in the sidebar again for the list to appear. It now loads its contents on reload like every other page.

_Under the hood:_ the carts list was the only page that triggered its data fetch from `afterNavigate` instead of `onMount`. Because the app shell (a CSR-only SPA) defers mounting page content until the auth bootstrap finishes, on a hard reload the initial "enter" navigation has already settled by the time the carts page mounts, so `afterNavigate`'s on-mount callback never fired and `load()` never ran. Switched it to `onMount`, matching every other route; returning from a cart's detail page still refreshes the list, since the two are separate routes and the list component remounts.

## [0.5.0] - 2026-07-09

**Phase 5 — carts (the functional heart): the two cart modes, computed totals, adjustments and the savings threshold. Opening with some catalog polish; the cart work lands below as it ships.**

### New

- **Carts.** Group catalog products into **carts** and see what they'd really cost. Two kinds: **cross-store** (any shop — the same product can appear once per shop, each row showing its store) and **single-store** (one shop, with that shop's discounts applied). A cart shows the full total, the discounted total, the shop's adjustments and a **final estimate**; you can set a **savings threshold** — enter it in € or as a %, and the two fields mirror each other on the current full total — with a progress bar, and the cart flags itself when it holds a **delisted** product. Fill a cart straight from the **Catalog** by selecting products and choosing a cart. Click a cart to open its **detail page** — a full product table with preview images, provenance per row and per-row remove.
- **TP Scraper test-data generator** (dev). The throwaway **TP Scraper** plugin page now has an **Add TP product** button (with a currency picker) that drops a random fake product — named `TP - …` — into your catalog, plus **Remove** and **Clear all**. It gives a second product source so **cross-store carts**, **delisting** and **currency-mismatch** rules can be exercised by hand without a second real shop.

### Changed

- **Release images also get a `latest` tag.** Each release now publishes both `watch-em-all` and `watch-em-all-ops` as `:x.y.z` **and** `:latest` on GHCR, so a `docker compose pull` can track the newest release without editing `WEA_VERSION` — pinning a version stays the recommended default, `latest` is the quick-try convenience.

### Fixed

- **Catalog — tighter category breadcrumb.** The category path no longer carries an unwanted gap around each `/` separator (`Giochi di Ruolo / GDR Italiano` → `Giochi di Ruolo/GDR Italiano`), matching the compact look the Dragon Store page already had.
- **Cart adjustment labels no longer show raw keys.** A cart's shop adjustments (e.g. Dragon Store's threshold discount and shipping) showed their internal i18n key (like `dragon_store.adjustments.threshold_discount`) instead of the translated label unless you had first opened that plugin's own page in the same session.

_Under the hood:_ the catalog breadcrumb markup is now packed with no whitespace between the inline elements — the SvelteKit template used to lay each segment on its own indented line and HTML collapsed those newlines into a rendered space; same approach the Dragon Store plugin page already used. The carts backend lands incrementally: this opens the core `carts`/`cart_members` tables and the cart API (`/api/carts`) — create with a fixed mode (`cross` / `scraper_specific`), list, rename, delete, plus membership add/remove. Membership is validated as a batch (your catalog only, no delisted products, one currency per cart, and only the cart's own scraper for `scraper_specific`); adds are idempotent. A read-only **Cart Engine** then computes each cart's state on demand — full / discounted totals over the active members, the adjustments (scraper_specific only) and the final estimate, plus an "unhealthy" flag when the cart holds a delisted product; the list returns cards, the detail adds the member rows. A cart also carries a **savings threshold** — an absolute € target stored on the cart (the percentage is only a UI input aid: the € and % fields now mirror each other, `threshold = full · (1 − pct/100)` on the current full total, and only the € value is sent); the engine marks it reached when the final estimate drops to it (and *partial* when reached with some members excluded). For a **Dragon Store** scraper-specific cart the engine now applies the shop's real rules: one non-cumulative threshold discount (5% over €100, 10% over €200, 15% over €300) plus shipping (+€5, free over €100), each shown as its own line in the cart. The product-table presentation is now a small set of shared widgets (`$lib/components`: thumbnail with hover-zoom, category breadcrumb, product cell, tags, discount badge, source chip) used by the Catalog, the cart detail and the scraper pages — one implementation, one look. The TP Scraper generator keeps its own `plugin_tp_scraper_products` table and, on every add/remove/clear, re-delivers the user's full set through the sanctioned Catalog Update Service (so removals delist rather than hard-delete); it deliberately stays non-schedulable (no `run_for_user`), so it never appears in the schedule editor or the worker. Finally, every mounted plugin's i18n dictionary is now registered eagerly at startup (during plugin discovery) rather than only when its page is first opened, so plugin-owned strings consumed by core routes — such as cart adjustment labels — always resolve.

## [0.4.0] - 2026-06-27

**Phase 4 — automatic scheduled scraping (the worker), plus the dev/admin tooling around it.**

### New

- **Scheduled scraping.** Set per-scraper daily times; the worker runs each scraper automatically, **one at a time**, catching up the last missed slot after downtime.
- **Schedule editor + 24-hour view.** A **Scrapers → Schedule** admin page sets each scraper's daily run times (HH:MM:SS chips, add/remove, suspend), with a **24-hour timeline** showing every run as a clickable plugin-icon marker and a live "now" marker on the server clock. Two runs must be at least 1 minute apart; removing a run asks for confirmation; a suspended scraper is grayed out everywhere.
- **Scrape cache.** Repeated page reads within a half-life come from a cache instead of the shop — fewer visits; an admin can clear a scraper's cache.
- **System log + page.** Worker/scraper events are recorded and read from a **System logs** admin page — a **Live** tail or paged **history**, with level tabs (counts), multi-source chips, message search and a context viewer; old logs and runs auto-prune after `log_retention_days` (price history never does).
- **System settings page.** A **Settings** admin page edits the runtime `system_settings` (run timeout, log retention, catch-up threshold, user-deletion grace) **without a restart** (`GET`/`PATCH /api/admin/settings`, ranges validated). **Feature flags** now lives as a child under Settings (a self-building dev page: worker-tick knob, non-persistent).
- **Scrapers & Notifiers admin.** Two admin areas list the loaded plugins by kind (icon + version): **Scrapers** also shows each scraper's schedule and opens its config page — politeness delay, HTTP timeout, cache half-life and the manual scrape-now cooldown — with a **Clear cache** button (changes apply on the next run, no restart); **Notifiers** lists the notifier plugins. (Replaces the earlier single Plugins list.)
- **Schema-drift safety net** (dev): a missing table/column surfaces in an **admin-only** banner/feed (`GET /api/admin/errors`), never on the public `/api/health`.

### Changed

- **Dev DB browser: Adminer → pgweb** — opens straight on the DB (no login); the **release** kit now carries **no** DB browser at all.
- **Heads-up — env vars renamed:** every variable is now **`WEA_`**-prefixed (e.g. `SECRET_KEY` → `WEA_SECRET_KEY`). Update your `.env`; see [`docs/env-variables.md`](docs/env-variables.md).

_Under the hood:_ a real `worker` (`src/worker`) ticks (interval from the `worker_tick` feature flag, re-read each second) and dispatches due slots to a **serial runner** under a per-scraper advisory lock shared with scrape-now (409 on overlap), with a run timeout from `system_settings` and `scrape_run`/`scrape_user_log` records. The scrape cache (`scrape_cache`, CTX-R9) and the system log (`system_log`) each sit behind a small **swappable interface** (`scrape_cache.py`, `system_log.py`) — Postgres today, a Redis backend later would be a localized swap; the worker drops expired cache at run start and prunes logs/runs past `log_retention_days` daily (price history never). Feature flags live in a `feature_flags` table shared by web and worker and cleared at web startup. Per-scraper operational settings live in `scraper_admin_config` (the core reserved keys), read by `build_context` for every run and scrape-now and superseding the former hard-coded constants and the `scrape_now_cooldown` dev flag. Schema drift iterates `Base.metadata` plus each plugin's declared `table_metadata` (DB-R7, enforced at load); pgweb is dev-only (no Compose profile, INF-3); env vars carry the `WEA_` prefix and the product version is baked from the git tag. A dev/CI **i18n consistency gate** (`src/frontend/scripts/i18n-check.mjs`, `npm run i18n:check`) checks the English translation JSONs (core + plugins) against the code — failing on a used-but-missing or defined-but-dead key — and runs on PRs and release tags; it flagged and removed ten orphaned strings (English is the reference; per-locale parity lands in phase 12).

## [0.3.4] - 2026-06-25

**Phase 3 — consolidation: close the open items and round off the documentation.**

- After the **forced first-login password change** you're now **signed in automatically** and taken straight to your home — no second trip through the login page.
- **Dragon Store** plugin:
  - bumped to **0.2.0**, marking the move from the initial mock to real `.gp` product scraping.

_Under the hood:_ the English wiki (`docs/`) gains the phase-3 canonical pages, translated from `docs-ita/` and limited to what is implemented (DOC-12): the `Product` contract, the Catalog Update Service, the scraper-plugin contract, the Catalog & Product Picker, and the Dragon Store plugin (overview / features / capabilities).

## [0.3.3] - 2026-06-23

**Phase 3 — real Dragon Store scraping, with a catalog that shows the real product.**

- **Scrape now** and the dry-run preview read the real product page: title, price, list price, availability, image, **brand** and **category**.
- Products carry their **brand** (a link to the shop when available), a **category** breadcrumb (each step clickable), and **tags** like _Edizione Limitata_, _Offerta Raven Prime_ or _Pre Order_ — shown in the Catalog, the watched list and the dry-run preview.
- Marketing/edition labels are stripped from the product name and shown as tags instead, so titles stay clean.
- Pre-order items ("Prossimamente") count as orderable and are tagged _Pre Order_; out-of-stock items are marked unavailable.
- **Watched products** now appear like the preview — image, title, brand, category and a tags column — with the product **title resolved as soon as you add it** (not just the URL).
- Adding a product **already watched** is rejected with a clear message.
- **Catalog** page: the photo enlarges on hover (after a short pause, so it doesn't pop up while you scroll past), the product photo/title link to the shop (the separate "Open" column is gone), the **source** links to its scraper page, the **tags** sit in their own column, and you can sort by source, list price and availability too. The **discount** shows as a `-NN%` badge **under the price** (no separate Discount column), and the list price is struck through only when there's an actual discount. It also fills in on its own right after a scrape — no need to hit Search, and the empty page no longer flickers while it retries.
- Each scraper shows its **icon** next to the title and in the menu.

_Under the hood:_ a new stdlib `context.http` client gives every scraper politeness, a timeout, an identifiable user-agent, a request counter and short retries with backoff (no new dependency). The Dragon Store parser reads the page's JSON-LD `Product` (primary, unambiguous) for most fields and the JSON-LD `BreadcrumbList` for the category, taking the list price from the detail table and decoding windows-1252 + HTML entities while ignoring the page's many related products. `Product` gains `brand` (text + optional link), `tags` (a generic tag list) and `category` (a breadcrumb of `{text, link}`); the base scraper supplies the `add_tag`/`get_tags` and `add_child`/`get_path` mechanisms (the `tags` field/column is the renamed, generic former "product properties"). The Catalog's dormant `discount_pct` sort option was dropped (the discount has no column to sort). The title sanitizer is Dragon-Store-specific (hand-maintained label list). The watched list is backed by a product snapshot stored on the watch (set on add, refreshed each run). Plugin icons are auto-detected at load (`plugin-icon.ico` → `.svg`). Plugin frontends live outside the SvelteKit root, so they're registered as Tailwind sources (`@source` in `app.css`) to ensure plugin-only utility classes ship in the built CSS. Verified offline against saved real-page fixtures.

## [0.3.2] - 2026-06-20

**Phase 3 — watch a Dragon Store product and find it in your catalog.**

- Watch a Dragon Store product by pasting its URL on the scraper's page.
- Preview what a scrape would find, without saving anything (dry-run).
- **Scrape now** pulls your watched products into the catalog on demand.
- Right after a scrape, **Scrape now** rests for a while — the button shows a countdown until it's available again.
- New **Catalog** page: your products in a searchable, sortable, paginated table — price, discount, availability, source, and a link to the shop.
- Tidied the shell: the empty top bar is gone, and the light/dark theme toggle now lives in **Profile → Settings**.

_Under the hood:_ the first scraper drives the catalog end-to-end with **mock** data — real product identity (from the site's native id), invented prices — so the whole flow works before the real parser arrives. Scrapers write only through the catalog service; the manual scrape is rate-limited per scraper by a cooldown (a constant for now, admin-configurable in phase 4). Product identity is a shared template-method, so a product keeps the same id across runs. Spec reworked accordingly (SCR-R15), plus an English future-improvements page; `tp_scraper` stays as a throwaway test plugin.

## [0.3.1] - 2026-06-19

**Phase 3 — groundwork for the catalog (nothing visible yet).**

- No user-facing change: this lays the foundations the catalog and scrapers build on.

_Under the hood:_ adds the `Product` contract every scraper produces and the catalog tables (`products` + an append-only `price_history`, per-user, identity `user_id + plugin_id + external_id`). The Catalog Update Service is the **single write path**: it fills in missing prices, classifies each change (new / updated / price change / delisted), records history only when price or availability changes, and delists products missing from a delivery — a reappearing one comes back. `GET /api/catalog` reads the user's catalog (paginated, sortable, filterable). Backend only, verified by unit/API tests.

## [0.3.0] - 2026-06-19

**Phase 3 — admins can create the accounts that use the app.**

- Admins create user accounts (username, name, role, a temporary password) and see them in a list.
- A new account must change its temporary password at first login.
- The app splits by role: admins get an admin area, regular users get their own — no mixing.
- No self-registration: only an admin creates accounts.

_Under the hood:_ `POST`/`GET /api/admin/users` (admin-only; duplicate username → 409), the forced first-login password change, and a role-based shell with a route guard (plugin discovery loads only for users). User management was pulled forward from phase 10 so a `user` account can exist before the catalog. Deferred to phase 10: reset password, disable/enable, soft-delete with grace + restore, status filters, last-login sort, courtesy notifications, the load dashboard.

## [0.2.0] - 2026-06-18

**Phase 2 — Plugin system.** Opened with post-0.1.0 polish; the plugin-system backbone is below.

### Fixed

- **Worker stops promptly on `docker stop`.** The stub worker runs as PID 1, which ignores signals that have no handler, so Docker waited the full ~10s stop timeout before SIGKILL. It now installs a SIGTERM/SIGINT handler and exits cleanly (verified: ~0.3s).

### Added

- **Plugin system — the dynamic backbone (phase 2).** Plugins are auto-discovered full-stack folders under `src/plugins/{scrapers,notifiers}/<name>/`, each described by a declarative `manifest.json`.
  - *Backend:* a manifest parser with validation (type ↔ folder, `api_version`, snake_case `name`, kebab `route_base`); a registry that loads the enabled plugins with **per-plugin failure isolation** (a broken plugin is rejected and logged — the app and the other plugins stay up); a minimal **Plugin Context** (own DB engine/session for `plugin_<name>_*` tables, namespaced logger, empty admin config — the logger/config are declared phase-2 stubs until `system_log` and the ConfigField infra land); `GET /api/plugins` discovery (no internal paths); each plugin mounts its router under `/api{route_base}` with a `Plugin: <name>` Swagger tag; icons served from `/api/plugin-assets/{name}/icon`.
  - *Frontend:* a `build:plugins` step generates the component registry from the manifests (gitignored, never hand-edited); a single catch-all route `plugins/[...rest]` mounts plugin pages dynamically; scrapers appear in a collapsible **SCRAPERS** sidebar group, notifiers never do; bundle/runtime mismatches are surfaced in the console, never as a broken page. Plugins import only via `$lib` (so they resolve from outside the SvelteKit root); the `$plugins` alias + Vite `fs.allow` let the single Vite build bundle them.
  - Ships two throwaway **Test Plugins** — TP Scraper (full-stack) and TP Notifier (backend-only) — that exercise the whole path; they will be removed when real plugins land.
- **Product version on the login page** too (small line under the form), fetched from `GET /api/health` — alongside the version already shown in the sidebar.
- **`docs/updates/phase-02.md`**: the phase-2 companion doc, including the browser command to preview the Italian translation (`localStorage.setItem('wea_lang','it')` + reload).
- **Autofocus** on the new-password field when the forced password-change page opens (verified: the focused element is `input[name=new-password]`).

### Changed

- **Dev and release stacks no longer share a database volume.** Distinct Compose project names — `compose-dev.yml` → `watch-em-all-dev`, `compose.yml` → `watch-em-all` — so each gets its own named volume regardless of the folder it runs from. `compose.yml` also documents (commented) how to switch the DB to a local bind mount if preferred.
- **Every functional API now sits behind authentication.** Only `/api/health`, `/api/auth/login`, `/api/auth/refresh` and the static plugin icon (`/api/plugin-assets/...`, loaded by the browser as an `<img>`) stay public; the plugin discovery and every plugin route now require a logged-in user. Each endpoint also carries a one-line English `summary` shown in Swagger.
- **Sidebar:** the brand is now "👀 Watch 'Em All"; the version line is a centered link that opens Swagger (`/api/docs`) in a new tab (same text, no other restyle).
- Removed obsolete `.gitkeep` placeholders now that `src/{core,web,frontend}` and the plugin folders carry real content (kept `src/worker/.gitkeep`, still empty until phase 4).

## [0.1.0] - 2026-06-17

**Phase 1 — Foundations.** The live skeleton: the real application, authentication and the SPA shell replace the phase-0 stubs. (Developed as a single batch on `main`; this entry consolidates the whole phase.)

### Added

- **Backend (FastAPI).** Config loader (1.B1): `config.yaml` + `.env` with `${VAR}` / `${VAR:-default}` interpolation, fail-fast validation, reads the baked product version. `GET /api/health` (1.B2): DB check + product version, Swagger at `/api/docs`, `{detail, code}` error envelope (BE-11). Users + initial-admin bootstrap (1.B3): `users` table with bcrypt hashing and **first/last name**, admin created from the environment with a forced password change. JWT auth (1.B4–1.B6): login/logout, refresh with `jti` rotation and reuse → 401 + global logout, `token_version` invalidation, the `must_change_password` gate (via an `mcp` access claim, no DB read), `account_disabled`, in-memory login rate limit. Profile (1.B7): `GET/PATCH /api/me` (id, username, first/last name, role, locale).
- **Frontend (SvelteKit 2 / Svelte 5 SPA, 1.F1–1.F5).** Scaffold + svelte-i18n (`en` complete fallback + `it`) + dark/light theme with no flash; Auth Manager (access in memory, refresh in localStorage, single-flight + proactive refresh); login → route guard → protected shell (sidebar + header); forced first password change (no current password) and the normal change (current required), both with a hidden username field for password managers; dashboard greeting by first name; profile showing Username / Name / Surname / Role; the product version shown small under *Log out*. The `web` image builds and serves the SPA (`spa.py`, client-side-routing fallback).
- **Version source of truth (1.T4).** The git tag: computed at build via `git describe` and baked into the image (`/app/VERSION`), exposed on `/api/health`; `pyproject.toml`/`package.json` keep an inert placeholder. A `publish.yml` guard verifies the tag matches the top CHANGELOG entry (the CHANGELOG is verified, not the source).
- **CI (1.T1).** `backend-checks` (ruff, `ruff format --check`, `mypy --strict`, pytest) and `frontend-checks` (`prettier --check`, `svelte-check`, build) on every PR.
- **Ops scripts (1.T2/1.T3).** Real `backup.sh` / `export.sh` / `restore.sh` (custom + plain dumps; restore verifies the archive, refuses while the app is connected, recreates the DB), replacing the phase-0 placeholders.
- Dev affordance: a `wea_lang` localStorage override to preview the Italian translation (no selector exposed in V1).

### Changed

- **Documentation pivots to English.** `docs/` becomes the English canonical wiki (grows phase by phase; the implemented phase-1 capabilities are written there), `docs-ita/` is the Italian source of truth during the transition (retired at v1). New `docs/updates/` holds per-phase, feature-level summaries with *Good to know* and *Useful Commands* (not linked from the wiki).
- **Single configuration source; composes at the repo root.** Both composes read `.env` (`env_file`), with no inline defaults — `.env.example` is the single source. `compose.yml` (the default) is the release/image compose; `compose-dev.yml` builds from sources; the `deploy/` folder is removed.
- `GET /api/me` is exempt from the must-change-password gate (it drives the SPA boot and carries the user's name).

### Fixed

- Frontend polish: svelte-i18n initialised at module load (no "set the initial locale" error); a page `<title>`; form `name` attributes; missing assets return a clean 404 instead of the SPA HTML; `replaceState` guard redirects; no throwaway `GET /api/me` 401 on reload (proactive refresh on boot).

## [0.0.17] - 2026-06-16

### Changed

- README **Releasing** section now spells out the correct order — **tag → build → release**: push the tag from the CLI, wait for the publish workflow to go green, then create the GitHub release on the *existing* tag. Publishing a release from the UI with a *new* tag would announce the version before its images are built (a window where `docker compose pull` fails). The deploy kit stays in the repo

### Docs

- **Phase 0 closed** (`phase-00-pipeline.md` → ✅, 0.T10 and the remaining DoD boxes ticked; flow index updated): the end-to-end pull-based cycle was exercised on `0.0.16` (tag → images on GHCR → release → clean install fetching the kit from the repo: `pull` + `up` → all healthy, `/api/health` 200)

## [0.0.16] - 2026-06-16

### Changed

- Deploy kit is **no longer attached as a release asset**: `deploy/compose.yml` and `.env.example` live in the repo and users fetch them at the release tag (raw URLs in the README install). This sidesteps GitHub's immutable releases entirely (no assets to freeze, no leading-dot asset-name issue) — a release can now be created freely from the **GitHub UI or the CLI**. The publish workflow's `release` job is **removed**: on a tag it only builds and pushes the two versioned images (`permissions` narrowed to `contents: read`). Supersedes the draft-staging approach from 0.0.15
- Docs realigned to "kit in the repo, not attached": README (Installation + Releasing), `deployment.md`, `ci.md` (IT + `docs-eng` mirror), `build-system.md` (IT + mirror), `INF-17`/`INF-19`, `phase-00`/`phase-12`

## [0.0.15] - 2026-06-16

### Changed

- Publish workflow is now **immutable-releases-safe** (GitHub made immutable releases the default: a published release's assets are frozen). The release job no longer creates a published release and then uploads the kit (which fails with `422 Cannot upload assets to an immutable release`). Instead it **stages a draft release with the deploy kit attached** and stops; the owner reviews, writes the notes and publishes it from the UI — at which point the release becomes immutable *with* the kit. The tag must be pushed from the CLI (drafts don't trigger workflows). Supersedes the idempotent-upload approach from 0.0.14
- Added a guardrail: if a **published** release already exists for the tag (released by hand from the UI), the job flips it to pre-release (best-effort, to avoid poisoning `/releases/latest`) and fails with clear instructions — a hand-published release can't receive the kit and that version is permanently reserved

### Added

- README **Releasing (maintainer)** section: a reminder of the manual release procedure (CLI tag → workflow stages the draft with the kit → publish from the UI) and the warning never to publish a release by hand from the UI

### Docs

- `ci.md` (IT + `docs-eng` mirror): the *tag and releases* section describes the new draft-staging procedure and the immutable-release caveat

## [0.0.14] - 2026-06-16

### Changed

- Publish workflow release step is now **idempotent**: if the release for the tag already exists (e.g. the tag was created by publishing a release from the GitHub UI), it only (re)attaches the deploy kit with `--clobber` instead of failing on `gh release create`. A tag pushed from the CLI still creates the release as before — so the owner can tag/release from the GitHub UI **or** the CLI. Docs aligned (ci.md); fixed a stale "three images" comment in the workflow header (it builds two)

## [0.0.13] - 2026-06-16

### Added

- README operations manual (0.T10, INF-18): the phase-0 operational sections — **Installation (pull-based)**, **Updating**, **Trying a dev image** — are filled with the real, tested commands (download the deploy kit, set `WEA_VERSION`, `docker compose pull && up -d`)
- English documentation (`docs-eng/infrastructure/`, DOC-12): English mirror of the four infrastructure docs implemented in phase 0 — `build-system`, `dev-container`, `ci`, `deployment` — describing only what exists (stub containers, the two-image build, CI/publish/cleanup, the pull-based deploy). `docs-eng` index updated accordingly

### Fixed

- Development compose: the `worker` service now **builds** the shared `watch-em-all:dev` image (via a YAML anchor on the `web` build) instead of only referencing it — a plain `docker compose up --build` no longer fails with `pull access denied` for the worker. The image is built once; the second build is a cache hit. Surfaced by the 0.T10 end-to-end dry run

## [0.0.12] - 2026-06-16

### Changed

- Healthchecks now use **curl everywhere** (dev + release compose): `curl` is installed in the app image (`packages/app/Dockerfile`, minimal — no recommends, apt lists wiped) and the `web` healthcheck switches from the Python stdlib probe to `curl -fsS http://localhost:8080/api/health`. One healthcheck command across dev and release — the previous python-in-dev / curl-in-release split is gone
- Worker heartbeat file now lives on a **`tmpfs`** (`/tmp` in RAM) in both composes: the per-tick write (CRON-R7 liveness) stays in memory and never reaches the disk. Cadence unchanged (60s tick, 180s stale threshold)

## [0.0.11] - 2026-06-16

### Fixed

- Dev-image cleanup now also removes the **orphan untagged manifest** left after unlinking a `dev-<branch>` tag (`delete-untagged: true`): previously each closed PR left behind a phantom `sha256:…` untagged version in GHCR, so the package filled up anyway. Release tags are never touched; safe because the images are single-arch

## [0.0.10] - 2026-06-16

### Fixed

- Dev-image cleanup no longer fails a PR close when the branch tag is the package's **only** version: GitHub forbids deleting the last tagged version of a package, so the cleanup step is now tolerant (`continue-on-error`). It's a transient case — it disappears once a release tag (`x.y.z`) is a permanent second version, after which dev-tag deletion always succeeds

## [0.0.9] - 2026-06-16

### Added

- Auto-cleanup of dev images (`.github/workflows/cleanup-dev-images.yml`): when a PR closes (merged or abandoned), the branch's `dev-<branch>` tag is deleted from the `watch-em-all` and `watch-em-all-ops` packages so GHCR does not fill up with stale dev tags. Only that tag is removed — release tags (`x.y.z`) are never touched. Uses the Actions `GITHUB_TOKEN` (falls back to a classic PAT with `delete:packages` if GitHub refuses to delete user-owned package versions)

### Changed

- Bump GitHub Actions to their Node 24 runtimes (Node 20 is deprecated): `actions/checkout` v4→v5, `docker/setup-buildx-action` v3→v4, `docker/login-action` v3→v4, `docker/build-push-action` v6→v7 in CI and publish

## [0.0.8] - 2026-06-15

### Changed

- Ship `web` and `worker` as a single image **`watch-em-all`** instead of two (`-web`/`-worker`): they share one codebase, one `pyproject`/lock and the same plugins — one application with two roles selected by the command (`web` | `worker`) via an entrypoint dispatcher. Published images drop from three to two (`watch-em-all` + `watch-em-all-ops`). `packages/web` + `packages/worker` merged into `packages/app`; both composes run web/worker from the same image via `command:`; CI and publish matrices updated (3 → 2); docs realigned (build-system, deployment, ci, developer-rules INF-17, phase-00)

### Fixed

- Disable buildx provenance attestations on push (`provenance: false` in CI and publish) — GHCR no longer shows a phantom `unknown/unknown` os/arch entry alongside each image

## [0.0.7] - 2026-06-15

### Added

- Base CI on PRs (`.github/workflows/ci.yml`, 0.T6): a CHANGELOG guard (PR fails if `CHANGELOG.md` is not updated — one PR = one version, INF-19) and a matrix job that builds the `web`/`worker`/`ops` images from the repo root. Linters/typecheck/tests come with the first code (1.T1)
- Dev images on PR (0.T7): the CI build job now pushes `web`/`worker`/`ops` to GHCR as `dev-<branch>` (branch slug, overwritten on each push) so a branch can be tried before merge; `workflow_dispatch` builds them on demand for branches without a PR (ci.md)
- Publish on tag + deploy kit (`.github/workflows/publish.yml`, 0.T9): an `x.y.z` tag (plain SemVer, no `v` prefix) — created by the owner by hand whenever a release is wanted — builds and pushes the three versioned images to GHCR and cuts the GitHub release with the deploy kit attached. Adds the kit files: `deploy/compose.yml` (release compose, image-based) and root `.env.example` (`WEA_VERSION` + `POSTGRES_*` + `ADMIN_INITIAL_PASSWORD`). Tagging is manual — there is no auto-tag workflow

## [0.0.6] - 2026-06-15

### Added

- Development compose (`docker-compose.yml`, 0.T5): the build-from-sources counterpart of the release deploy kit — `db` + `web` + `worker`, with `adminer` under profile `dev` (`:8081`) and the ephemeral `ops` under profile `ops`. Healthcheck on every long-running service and `json-file` log rotation everywhere (INF-2). Dev defaults on the DB env (`watchemall`) so `docker compose up` works without a `.env`; override via a local `.env`. The `web` stub healthcheck probes with the Python stdlib (the slim image ships no `curl`) — the release compose keeps `curl` for the real image (0.T9)

## [0.0.5] - 2026-06-13

### Removed

- GitHub CLI from the dev container (Dockerfile block + auth volume): git/GitHub operations (commit, push, PR) happen from the **host** by decision — the dev container only builds and runs. `gh` is installed on the host instead (declared exception to zero-install). Docs aligned (dev-container.md text + diagram, phase-00 0.T2)

## [0.0.4] - 2026-06-13

### Added

- Stub `worker` container (0.T4): heartbeat loop touching the file the compose healthcheck watches — declared mock, replaced by the real dispatcher/runner in 4.B1
- Stub `ops` container (0.T4): `postgres:16` + placeholder `ops/backup.sh`, `ops/export.sh`, `ops/restore.sh` (clear "not implemented yet" message, exit 1) — real scripts arrive with 1.T2/1.T3 and bake into the same image unchanged

## [0.0.3] - 2026-06-13

### Added

- Stub `web` container (0.T3): `packages/web/` multi-stage Dockerfile + stdlib placeholder server — "coming soon" page and `GET /api/health` always 200 (declared mock, replaced by the real app in 1.B2)
- Root `.dockerignore` (images build from the repo root)
- Dev-container architecture diagram in `docs/infrastructure/dev-container.md`

### Changed

- Tagging model (supersedes per-PR tags): versions still bump on every PR in the CHANGELOG, but release tags are created automatically only when a development-flow phase closes — 13 phases → 13 tags. Docs aligned (INF-19, ci, process rules); the auto-tag workflow lands as MVP 0.T8.

## [0.0.2] - 2026-06-13

### Added

- Dev container (`.devcontainer/`): Python 3.12 + Poetry, Node 22 + npm, git, Docker CLI + Compose plugin, GitHub CLI (0.T2)
- docker-outside-of-docker socket mount; named volume so `gh` auth survives container rebuilds; tolerant post-create that activates by itself once the toolchain files land (1.B1, 1.F1)
- `.gitattributes` forcing LF on `*.sh` (scripts run inside Linux containers; a CRLF checkout on Windows must never reach them)

## [0.0.1] - 2026-06-13

### Added

- Monorepo folder skeleton (`src/`, `packages/`, `ops/`, `deploy/`) as designed in `docs/infrastructure/build-system.md` (0.T1)
- `CHANGELOG.md` and the README operations-manual stub sections
- Project-specific `.gitignore` entries (frontend, backup archives, generated files) and root-anchored `lib/` so SvelteKit's `src/lib` is not ignored
