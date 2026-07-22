# Frontend — Pagine spec-ahead

> **Layer 4 — Capability** · Audience: developer · Riferimenti tecnici ammessi. UX: [user-experience](../../1-business/user-experience.md).
>
> Lo **stack**, la **struttura**, la **sequenza di boot**, la **shell/navigazione**, tema/lingua e le **pagine già rilasciate** (Dashboard, Login, Cambio forzato, Profilo, Product Picker, Carrelli, area admin: System logs, Utenti, Scrapers + Schedule, Notifiers, Settings + Feature flags) sono documentate in inglese in [`docs/4-capabilities/frontend/app-shell.md`](../../../docs/4-capabilities/frontend/app-shell.md). Restano qui solo le pagine ancora **spec-ahead** (fasi 6+) e i componenti che arrivano con loro.

## Pagine utente (spec-ahead)

| Pagina | Responsabilità | Feature di riferimento |
|---|---|---|
| Storico prezzi | **un componente grafico unico** (serie prodotto o carrello, selettori week/month/all, gap di indisponibilità) | [price-history](../../3-features/user/price-history.md) |
| Storico alert | elenco paginato, letto/non letto, categorie sistema/admin (notifiche admin con icona e colore dedicati), render Markdown dei messaggi testuali, dettaglio con esiti di consegna per canale | [alerts](../../3-features/user/alerts-and-notifications.md) |

La voce **Storico prezzi** e **Storico alert** (con badge non letti) si aggiungono alla sidebar utente quando le pagine arrivano.

## Pagine admin (spec-ahead)

| Pagina | Responsabilità |
|---|---|
| Dashboard di sistema | statistiche globali e ranking per utente — solo aggregati, mai contenuti ([admin-dashboard](../../3-features/admin/admin-dashboard.md)) |
| Monitoraggio scrapers | ultima run, trend, elenco run, drill-down per utente |
| Notifiche agli utenti | composizione Markdown con anteprima live, invio a tutti/un utente, elenco inviati con esiti; tab **messaggi di sistema**: catalogo template con override/ripristino, stesso editor ([admin-notifications](../../3-features/admin/admin-notifications.md)) |
| Manutenzione | purge storico alert per data |

## Componenti condivisi (spec-ahead)

- **Grafico storico**: unico componente, due sorgenti dati (serie prodotto o carrello).
- **Markdown**: un componente di render (markdown-it + DOMPurify, usato da Storico alert e anteprima) e l'editor textbox+anteprima della pagina admin di notifica.
- **Card carrello — tipi di alert**: la sezione dei tipi di alert per-carrello si aggiunge alla card ([carts](../../3-features/user/carts.md)) in fase 6.
