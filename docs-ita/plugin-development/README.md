# Sviluppare un plugin — Getting started

> Audience: **plugin developer**. Guida autosufficiente; pseudocodice e riferimenti al codice ammessi.

Questa sezione è tutto ciò che serve per scrivere un plugin senza leggere il resto della wiki (i rimandi sono approfondimenti, non prerequisiti).

## Cosa stai per costruire

Un plugin è una cartella autosufficiente con backend Python e frontend Svelte, descritta da un `manifest.json`. Due famiglie:

- **Scraper**: osserva un sito e-commerce e consegna prodotti al core → [scraper-development-guide.md](scraper-development-guide.md)
- **Notifier**: consegna le notifiche su un canale → [notifier-development-guide.md](notifier-development-guide.md)

In entrambi i casi il tuo plugin sarà **configurabile a due livelli** (admin: parametri di sistema; utente: parametri personali) tramite schemi dichiarativi: i form li disegna il core, tu dichiari i campi.

## Struttura della cartella

```
src/plugins/<scrapers|notifiers>/<nome_plugin>/
├── manifest.json
├── backend/
│   ├── __init__.py        # esporta l'istanza del plugin
│   ├── plugin.py          # la classe (ScraperPlugin / NotifierPlugin)
│   ├── routes.py          # router FastAPI del plugin (se serve)
│   └── i18n/              # solo notifier: testi delle notifiche (V1: en.json, sempre presente)
└── frontend/
    ├── index.ts           # export default { component }
    ├── *.svelte           # le tue pagine/componenti
    ├── assets/icon.svg    # icona del plugin (provenienza in UI)
    └── i18n/              # traduzioni UI, namespace dedicato (V1: en.json, sempre presente)
```

## Il manifest

```json
{
  "name": "nome_plugin",
  "display_name": "Nome leggibile",
  "type": "scraper",
  "version": "1.0.0",
  "api_version": 1,
  "enabled": true,
  "icon": "frontend/assets/icon.svg",
  "backend":  { "entry": "backend/__init__.py" },
  "frontend": { "entry": "frontend/index.ts",
                "route_base": "/plugins/nome-plugin",
                "i18n": "frontend/i18n" }
}
```

Tutti i campi e le regole di validazione: [manifest-reference.md](../../docs/plugin-development/manifest-reference.md).

## Il ciclo di vita

1. **Discovery**: all'avvio il core trova la tua cartella, valida il manifest, importa il backend.
2. **`initialize(context)`**: ricevi il [Plugin Context](../4-capabilities/core/plugin-context.md) — qui crei le tue tabelle (idempotenti, naming `plugin_<nome>_*`).
3. **Route**: il tuo router è montato sotto `/api/plugins/<route_base>` e compare nello Swagger.
4. **Frontend**: il tuo componente è montato sulla tua route; la voce in sidebar (scraper) appare da sola.
5. **Esecuzione**: il core ti invoca secondo il contratto della tua famiglia.

## Le tre regole d'oro

1. **Usa solo il contesto**: HTTP solo via `context.http` (politeness e conteggi sono imposti lì), DB solo sulle tue tabelle, log via `context.logger`. Niente import di runtime globali.
2. **Mai scrivere nel catalogo core**: per gli scraper l'unica via è `context.update_catalog(...)`.
3. **L'`external_id` è sacro** (scraper): stabile e univoco, o lo storico dei tuoi utenti si spezza. Tu implementi **solo** il seme (`identity_seed`); normalizzazione e hashing li impone la base, identici per tutti. Non riempire mai `external_id` a mano.

## Attivazione e test

- Metti `enabled: true`, poi **rebuild + restart** (`docker compose build && docker compose up -d`): il frontend è cucinato nel bundle a build time.
- Prima del rilascio passa la [checklist](checklist-and-testing.md): include i test di contratto che la CI esegue su ogni plugin.

## Cosa leggere dopo

| Documento | Quando |
|---|---|
| [manifest-reference.md](../../docs/plugin-development/manifest-reference.md) | sempre |
| [scraper-development-guide.md](scraper-development-guide.md) | se scrivi uno scraper |
| [notifier-development-guide.md](notifier-development-guide.md) | se scrivi un notifier |
| [checklist-and-testing.md](checklist-and-testing.md) | prima del rilascio |
| [Esempi reali](../implemented-plugins/) | come riferimento concreto |
