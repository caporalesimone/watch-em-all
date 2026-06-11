# Frontend — App shell e pagine

> **Layer 4 — Capability** · Audience: developer · Riferimenti tecnici ammessi. UX: [user-experience](../../1-business/user-experience.md).

## Stack

SvelteKit in modalità **SPA** (CSR, adapter-static con fallback; nessun SSR: app dietro login, plugin montati dinamicamente lato client), TypeScript strict, Tailwind CSS (dark mode a classe), Svelte stores, Fetch API via Auth Manager, Zod per la validazione client, Day.js. Build unificato app+plugin ([build-system](../../infrastructure/build-system.md)).

## Struttura

```
src/frontend/src/
├── routes/            # +layout.svelte (shell), dashboard/, picker/, carts/,
│                      # history/, alerts/, profile/, admin/, plugins/[...]
├── lib/
│   ├── components/    # design system condiviso (anche per i plugin: $lib/components)
│   ├── stores/        # auth, theme, locale, plugins
│   ├── api/           # client tipizzati per endpoint (usa lib/auth)
│   └── auth/          # Auth Manager
├── generated/         # plugin-registry.ts (GENERATO, mai a mano)
└── locales/           # it.json, en.json (core); i plugin hanno i propri namespace
```

## Shell e navigazione

- **Sidebar sinistra persistente**: Dashboard · Product Picker · Carrelli · Storico prezzi · Storico alert (badge non letti) · Profilo · *(separatore)* · gruppo **SCRAPERS** collassabile (default aperto), **ultimo** così cresce senza spostare le voci core; voci dinamiche da `GET /api/plugins` con icona e route del plugin.
- **Header**: toggle tema e lingua. I notifier **non** sono in nav (stanno in Profilo).
- **Area admin**: sezione separata visibile solo con ruolo admin (dashboard di sistema, utenti, scheduler, monitoraggio, config plugin, log, impostazioni).

## Tema e lingua

- Tema chiaro/scuro, **default scuro**; preferenza per-browser in `localStorage`, applicata **prima del primo render** (niente flash). Dark mode Tailwind con classe su `<html>`.
- Lingua: per-account (`users.locale`), ricevuta al login e applicata al boot; il toggle in header la persiste via `PATCH /api/me`. Le traduzioni dei plugin vivono in namespace dedicati caricati con i loro componenti.

## Pagine utente (mappa di responsabilità)

| Pagina | Responsabilità | Feature di riferimento |
|---|---|---|
| Dashboard | stato carrelli, badge alert non letti, banner "nessun notifier attivo" | — |
| Product Picker | tabella catalogo paginata server-side; provenienza; azioni di pulizia; scrape-now a catalogo vuoto | [catalog](../../3-features/user/catalog-and-product-picker.md) |
| Carrelli | card dei carrelli, creazione/modifica, tipi di alert, soglie | [carts](../../3-features/user/carts.md) |
| Storico prezzi | **un componente grafico unico** (serie prodotto o carrello, selettori week/month/all, gap) | [price-history](../../3-features/user/price-history.md) |
| Storico alert | elenco paginato, letto/non letto, categorie sistema/admin (notifiche admin con icona e colore dedicati), dettaglio con esiti di consegna per canale | [alerts](../../3-features/user/alerts-and-notifications.md) |
| Profilo | password, lingua, cadenza, summary, canali notifier (form dinamici + test + flag) | [profile](../../3-features/user/profile-and-notifiers.md) |
| Pagine plugin | montate dinamicamente sotto la route del plugin | [plugin-discovery](plugin-discovery.md) |

## Pagine admin

| Pagina | Responsabilità |
|---|---|
| Dashboard di sistema | statistiche globali e ranking per utente — solo aggregati, mai contenuti ([admin-dashboard](../../3-features/admin/admin-dashboard.md)) |
| Utenti | CRUD account, reset password, disabilitazione |
| Scheduler scrapers | slot 1..N per scraper, sospensione, impostazioni globali (pool, timeout, retention) |
| Monitoraggio scrapers | ultima run, trend, elenco run, drill-down per utente |
| Config plugin | pagine admin dei plugin (form dinamici + Test Scraper / test canale) |
| Notifiche agli utenti | composizione e invio messaggi a tutti/un utente, elenco inviati con esiti ([admin-notifications](../../3-features/admin/admin-notifications.md)) |
| Log di sistema | polling incrementale con cursore, filtri, heartbeat del worker evidenziato |
| Manutenzione | purge storico alert per data |

## Componenti condivisi rilevanti

- **Tabella prodotti** (Product Picker + risultati dry-run dei plugin): colonne standard, ordinamento, provenienza.
- **Form dinamico da `ConfigField[]`**: un componente per tutti i form di config dei plugin (admin e utente), con gestione campi secret (`is_set`, write-only) e bottone Test per i notifier.
- **Grafico storico**: unico componente, due sorgenti dati.
- **Card carrello**: layout della card ([carts](../../3-features/user/carts.md)).
