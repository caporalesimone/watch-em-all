# Future Proposals & Ideas

> A parking lot for **ideas worth keeping in mind**, to revisit **after the whole project is built** (post-1.0). These are *ideas, not todos*: nothing here is committed, scheduled, or required for any phase. Some will be promoted to real specs, some refined, some dropped. The point is not to lose a good thought just because it does not fit the current scope.
>
> This differs from the per-phase [deliberately-deferred backlog](../../docs-ita/future-improvements/README.md) (items postponed *with a trigger* that promotes them): those are decisions; these are open possibilities. When an idea here is taken on, it is specified in the proper wiki layers and removed from this page.

## Index of ideas

| # | Idea | One line |
|---|---|---|
| 1 | [Richer "Scrape now" cooldown affordance](#1--richer-scrape-now-cooldown-affordance) | Countdown-in-label + progress bar instead of the plain disabled button |
| 2 | [Catalog-level "Scrape all" button](#2--catalog-level-scrape-all-button) | One click in the Product Picker to refresh every scraper not in cooldown |

---

## 1 — Richer "Scrape now" cooldown affordance

**Context.** Each scraper page has a per-scraper **Scrape now** button. It is rate-limited by a per-scraper **cooldown** (minimum interval between two manual scrapes, server-enforced, returns `429` with the remaining time). The shipped MVP uses the **sober treatment**: the button stays disabled with its normal label and a small muted caption underneath — *"Next scrape in 42 min"* — plus a tooltip explaining the rule. The cooldown state is read from the plugin's `GET …/scrape-now` (`{available, available_at, interval_seconds}`); the client countdown is purely cosmetic.

**The idea.** A more expressive, more reassuring treatment when the button is locked:

- **Countdown inside the label** — the button label becomes the live timer, e.g. `Available in 42:15`, with a clock icon, reverting to **Scrape now** when it reaches zero.
- **Determinate progress bar** — a thin bar under (or around) the button that **fills as the cooldown elapses**, giving an at-a-glance sense of "almost there" without reading numbers:

  ```
  ┌──────────────────────────────┐
  │  ⏳  Available in 42:15        │   ← disabled
  └──────────────────────────────┘
     ▓▓▓▓▓▓▓▓░░░░░░░░░░
     Manual scrape: once every 1 hour
  ```

- **Adaptive time format** — `1 h 03 min` when far out (ticks per minute), `42 min` in the mid range, `1:30` (mm:ss, ticks per second) in the final couple of minutes.
- **Becomes-available cue** — a subtle pulse / colour shift the moment it unlocks, so a user who is watching the page notices without refreshing.

**Why deferred.** It is pure polish: the sober version already communicates *when* and *why*. The richer one is presentation only — **the server stays the single source of truth** (the timer never decides anything; the `POST` re-validates and a stale client snaps back to the server's `available_at`). Worth doing once the product is otherwise complete and we are tuning the feel.

---

## 2 — Catalog-level "Scrape all" button

**Context.** Today **Scrape now is per-scraper**: it lives on each scraper's own page and runs *that one* scraper for the requesting user. This was a deliberate choice — the core never fans out over scrapers, so it never runs a scraper for a user who did not configure it, and the "empty delivery delists the catalog" hazard cannot arise. The catalog (Product Picker) only *reads*; its empty-state points users to the scraper pages.

**The idea.** Add a **single button in the Product Picker** — *"Refresh all" / "Scrape all"* — that, in one click, triggers **every scraper the user has configured that is not currently in cooldown**, instead of visiting each scraper page in turn. Convenience for a user who watches several stores and just wants a fresh catalog.

**Sketch of behaviour.**

- Fans out over the user's configured scrapers (the core asks each scraper *"is this user configured?"* — the same per-user dispatch the scheduled runner uses; the core still never reads plugin tables directly).
- **Skips** scrapers that are in cooldown or not configured, and **reports per-scraper outcome**: *started* / *skipped — in cooldown until 14:30* / *skipped — not configured*.
- The per-scraper **cooldown stays the unit of rate-limiting** and stays **server-enforced**; this button only orchestrates the ones that are eligible.
- Natural home: a secondary action in the Product Picker toolbar, and possibly the catalog empty-state ("configure a scraper, then refresh everything here").

**Why deferred.** With a single scraper it adds nothing over the per-scraper button. It becomes valuable only once a user realistically runs **several** scrapers — at which point the fan-out, the per-scraper skip/cooldown reporting, and the shared dispatch with the scheduled runner are all worth building together. Captured here so the rejected "one button runs everything" model is not lost: it is a good *future* shape, just not the *first* one.
