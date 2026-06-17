# Storico prezzi (lato utente)

> **Layer 3 — Feature utente** · Audience: architetti, developer · Testo + Mermaid, niente codice. Capability: [price-history](../../4-capabilities/core/price-history.md).

## Scopo

Mostrare l'andamento nel tempo di prezzi e disponibilità, per giudicare se l'offerta di oggi è un minimo reale. Due viste — **per prodotto** e **per carrello** — rese dallo **stesso componente grafico** (cambia solo la serie di dati). Gli indicatori derivati (minimo storico, statistiche, convenienza) sono una feature a sé: [price-analytics.md](price-analytics.md).

## Principio di registrazione (semplificato by design)

Lo storico registra una entry **solo quando qualcosa cambia**: il prezzo **oppure** la disponibilità. Niente snapshot periodici. Ogni entry porta prezzo corrente, listino, sconto e stato di disponibilità: una sola tabella append-only copre sia la linea del prezzo sia i periodi di indisponibilità, senza infrastruttura aggiuntiva.

## Requisiti

- **HIST-R1** — Entry scritta dal core al cambio di prezzo **o** di disponibilità; mai dallo scraper direttamente.
- **HIST-R2** — Il grafico prodotto mostra la linea del **prezzo scontato**; nei periodi in cui il prodotto risulta non disponibile la linea mostra un **gap esplicito** (nessuna interpolazione), derivato dallo stato di disponibilità registrato nelle entry.
- **HIST-R3** — Selettori temporali: **Week** (7 giorni), **Month** (30 giorni), **All**.
- **HIST-R4** — Il grafico di **carrello** proietta la **composizione attuale** del carrello sullo storico: somma dei prezzi scontati dei membri correnti, con i prodotti non disponibili esclusi nei rispettivi intervalli. *Semplificazione dichiarata*: non si ricostruisce la composizione passata del carrello (chi c'era e chi no in una certa data) — servirebbe lo storico delle appartenenze, complessità non giustificata.
- **HIST-R5** — Lo storico di un prodotto si elimina solo con il prodotto (pulizia del catalogo); nessuna retention automatica: il valore dello storico cresce nel tempo ed è il motivo per cui il sistema esiste.
- **HIST-R6** — Accesso dal Product Picker (riga → grafico prodotto), dalla card del carrello (azione → grafico carrello) e dalla pagina Storico prezzi.

## Viste

```mermaid
flowchart LR
    subgraph "Vista prodotto"
        P[Serie: prezzo scontato del prodotto<br/>+ gap di indisponibilità]
    end
    subgraph "Vista carrello"
        C[Serie: somma prezzi scontati<br/>dei membri attuali del carrello]
    end
    CMP[Componente grafico unico<br/>selettori Week / Month / All<br/>tooltip con data, prezzo, disponibilità]
    P --> CMP
    C --> CMP
```

## Lettura delle serie

Le entry sono **punti di variazione**: il grafico li unisce a gradini (il prezzo resta costante tra due variazioni). Un intervallo senza entry non significa "dati mancanti": significa "niente è cambiato" — che è esattamente l'informazione che il selettore *All* rende leggibile sulle lunghe distanze.
