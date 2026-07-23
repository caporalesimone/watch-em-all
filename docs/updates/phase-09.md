# Phase 9 — Dragon Store, complete 🐉

> Feature-level recap. Phase 9 takes the first scraper from "one product at a time" to a full
> configuration: paste a **category URL**, preview it with a **dry-run**, confirm — and dozens of
> products flow into your catalog on every run, with de-duplication and the site's own exclusions
> applied. Delisted products **grey out on their own** and clear with a click.
>
> 🚧 **In progress (0.9.x).** This page fills in as the phase's MVPs ship; the list below tracks
> what has actually landed.

## What's implemented (0.9.0)

_Nothing merged yet — entries land here as each MVP ships._

<!--
As MVPs land, document them here in the same user-facing voice as the earlier phases, e.g.:

### 1) Category scraping (pagination + de-dup + site exclusions)
### 2) Add-URL with dry-run preview
### 3) Catalog lifecycle (delisting + cleanups)
### 4) Full Dragon Store user UI

_Under the hood:_ …
-->

## Good to know

- **A category can bring in many products at once**, page after page — de-duplicated, with the
  store's own exclusions respected.
- **Delisting is non-destructive:** products that vanish from the site are greyed out, not deleted,
  and you decide when to clear them.

## Useful Commands

```bash
docker compose -f compose-dev.yml up -d --build         # db + web + worker + pgweb + mailpit
```
