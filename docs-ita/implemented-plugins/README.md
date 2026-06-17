# Implemented Plugins

> Documentazione dei **plugin reali** dell'installazione. La documentazione generica del sistema descrive solo i contratti astratti ([scraper](../3-features/plugins/scraper-plugin.md), [notifier](../3-features/plugins/notifier-plugin.md)); tutto ciò che è specifico di un sito o di un canale vive qui.

## Plugin

| Plugin | Tipo | Stato | Documenti |
|---|---|---|---|
| **Dragon Store** | scraper | primo scraper, riferimento per i futuri | [dragon-store/](dragon-store/overview.md) |
| **Email** | notifier | primo notifier previsto | [notifiers/email.md](notifiers/email.md) |
| **Discord** | notifier | pianificato (placeholder) | [notifiers/discord.md](notifiers/discord.md) |

## Struttura della doc di un plugin

Ricalca i layer della wiki, in piccolo:

- **overview** — cosa fa, per chi, stato (≈ layer 1-2)
- **features** — comportamento dettagliato specifico del sito/canale (≈ layer 3)
- **capabilities** — dettagli tecnici, tabelle, strategie, punti aperti (≈ layer 4)

Per i notifier, più compatti, un documento unico per plugin.

## Regola

Quando si rilascia un nuovo plugin, la sua documentazione qui è parte della [checklist di rilascio](../plugin-development/checklist-and-testing.md). Un plugin non documentato non si rilascia.
