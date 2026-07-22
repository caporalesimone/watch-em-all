# Implemented Plugins

> Documentation of the installation's **real plugins**. The generic system documentation describes only the abstract contracts ([scraper](../3-features/plugins/scraper-plugin.md), notifier — spec-ahead, [`docs-ita`](../../docs-ita/3-features/plugins/notifier-plugin.md)); everything specific to a site or a channel lives here.
>
> English translation of the Italian reference [`docs-ita/implemented-plugins/README.md`](../../docs-ita/implemented-plugins/README.md), limited to what is implemented (DOC-12). Today that is one plugin — the Dragon Store scraper. The planned notifier plugins (Email, Discord) are still spec-ahead and documented in Italian.

## Plugins

| Plugin | Type | Status | Documents |
|---|---|---|---|
| **Dragon Store** | scraper | first scraper, reference for the future ones | [dragon-store/](dragon-store/overview.md) |

## Structure of a plugin's docs

Mirrors the wiki's layers, in miniature:

- **overview** — what it does, who it is for, status (≈ layers 1-2)
- **features** — detailed site/channel-specific behaviour (≈ layer 3)
- **capabilities** — technical details, tables, strategies, open points (≈ layer 4)

Notifiers, being more compact, get a single document per plugin.

## Rule

When a new plugin is released, its documentation here is part of the release checklist (spec-ahead, [`docs-ita`](../../docs-ita/plugin-development/checklist-and-testing.md)). An undocumented plugin is not released.
