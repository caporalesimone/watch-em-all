# Plugin Context — estensioni spec-ahead

> **Layer 4 — Capability** · Audience: developer · Pseudocodice ammesso. Architettura: [plugin-architecture](../../2-architecture/plugin-architecture.md) (trust model).
>
> Il contesto già rilasciato (`engine`, `db`, `logger`, `config`, `update_catalog`, `http` con cache di scrape CTX-R1..R9) è documentato in inglese in [`docs/4-capabilities/core/plugin-context.md`](../../../docs/4-capabilities/core/plugin-context.md). Restano qui solo le estensioni ancora **spec-ahead**: gli helper per le notifiche (`markdown`, `locale_of` — fase 6) e la semantica dei **form dinamici** del `config` (ConfigField — fase 7+).

## `markdown` (fase 6)

I `body` dei messaggi testuali (`TextMessageEvent`, [alert-event](../contracts/alert-event.md) AEV-R7) sono **Markdown**; il render è centralizzato nel core, mai reimplementato dai plugin.

```python
class MarkdownHelper:
    def to_html(self, md: str) -> str: ...   # markdown-it-py + sanificazione nh3
    def strip(self, md: str) -> str: ...     # testo puro per i canali senza formattazione
```

- **CTX-R8** — Il notifier rende il Markdown **solo** tramite questi helper: l'HTML in uscita è sempre sanificato (niente HTML inline passante), e il comportamento sintattico è identico su tutti i canali e coerente con l'anteprima frontend (parser della stessa famiglia markdown-it).

## `locale_of` (fase 6)

`locale_of(user_id) -> locale`: la lingua del destinatario, usata per i testi delle notifiche.

## `config`: form dinamici (fase 7+)

La sezione **admin** del plugin è persistita nelle tabelle core (`scraper_admin_config`/`notifier_admin_config`) e gestita dalla UI admin via [ConfigField](../contracts/config-field.md). Nelle fasi rilasciate `config` espone i soli **valori riservati del core** (politeness, timeout, emivita della cache), letti dal core; i **campi dichiarati dal plugin** — via `get_admin_config_schema()`/`get_user_config_schema()` come `list[ConfigField]` — arrivano con l'infrastruttura ConfigField. La config **utente** degli scraper vive nelle tabelle del plugin; quella dei notifier arriva già mergeata alla `send()`.
