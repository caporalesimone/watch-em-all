# Developer Rules — Frontend (Svelte/TypeScript)

> Vincolanti per la SPA e per i frontend dei plugin. Capability: [app-shell](../../4-capabilities/frontend/app-shell.md).

## Stile e tipi

- **FE-1** — TypeScript **strict**; `eslint`, `prettier` e `svelte-check` puliti in CI. Niente `any` nei moduli condivisi.
- **FE-2** — Componenti piccoli e a responsabilità unica; la logica non banale vive in moduli TS testabili, non negli script dei componenti.
- **FE-3** — Naming: `PascalCase.svelte` per i componenti, `camelCase` per funzioni/store, kebab-case per le route.

## Architettura della SPA

- **FE-4** — **Mai `fetch` diretto**: tutte le chiamate passano dal client di `lib/api/` (tipizzato per endpoint), che usa l'[Auth Manager](../../4-capabilities/frontend/auth-manager.md). Nessun componente conosce i token.
- **FE-5** — Stato condiviso solo negli store di `lib/stores/`; gli store non fanno I/O da soli (lo fanno le action che li popolano).
- **FE-6** — Tipi delle risposte API allineati ai contratti Pydantic (Decimal = string!), validati con Zod ai confini quando il dato guida logica critica (prezzi, soglie).
- **FE-7** — Elenchi potenzialmente lunghi (catalogo, storici, run): **sempre** paginazione server-side; mai caricare "tutto" e filtrare in client.

## Design system e UX

- **FE-8** — Componenti riusabili in `$lib/components`; un pattern usato due volte si estrae. I plugin **devono** usare il design system (niente stili paralleli).
- **FE-9** — Tailwind con dark mode a classe; ogni componente si testa in entrambi i temi; default scuro, tema applicato prima del primo render (niente flash).
- **FE-10** — La **provenienza** (icona scraper) si mostra ovunque compaia un prodotto: Product Picker, carrelli, notifiche, anteprime. Non è opzionale (UC-2).
- **FE-11** — Azioni distruttive (svuota catalogo, elimina carrello/account): conferma con **conseguenze esplicite** nel testo.
- **FE-12** — Stati vuoti curati: catalogo vuoto (con scrape-now), nessun carrello, nessuna notifica — mai una tabella bianca senza guida.

## i18n e formati

- **FE-13** — Nessuna stringa cablata nei componenti: tutto da chiavi di traduzione nelle cartelle **`i18n/`** (core o namespace del plugin). **V1 spedisce solo `en`** (English-first): ogni stringa nuova nasce in `en.json`, che deve sempre esistere ed essere completo (è il **fallback** quando una lingua manca); le altre lingue sono riempimento futuro dei file, mai refactor. Mai costruire frasi per concatenazione di chiavi (l'ordine delle parole cambia tra lingue): sempre template interi con placeholder.
- **FE-14** — Date con Day.js; prezzi formattati da un'unica utility (simbolo valuta, 2 decimali); attenzione alla convenzione weekday (0=lunedì dal backend ↔ `getDay()` JS parte da domenica: si mappa in un solo punto).

## Plugin frontend

- **FE-15** — Entry contract: `export default { component }`. La route viene dal manifest, mai dichiarata nel codice.
- **FE-16** — Import dal core solo via `$lib` (design system, store, api client); mai percorsi relativi verso l'app.
- **FE-17** — Le traduzioni del plugin vivono nel suo namespace; mai toccare i file lingua del core.
