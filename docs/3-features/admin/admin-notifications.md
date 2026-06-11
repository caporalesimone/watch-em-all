# Notifiche admin agli utenti

> **Layer 3 — Feature admin** · Audience: architetti, developer · Testo + Mermaid, niente codice. Architettura: [notification-architecture](../../2-architecture/notification-architecture.md) · Capability: [alert-event](../../4-capabilities/contracts/alert-event.md), [database](../../4-capabilities/database/schema.md). Feature correlate: [alerts-and-notifications](../user/alerts-and-notifications.md), [plugin-configuration](plugin-configuration.md).

## Scopo

Dare all'admin un canale di comunicazione verso gli utenti **dentro l'infrastruttura di notifica esistente**: una pagina da cui scrivere un messaggio (titolo + testo) e inviarlo a **tutti gli utenti** o a **un utente specifico**. Casi d'uso tipici: manutenzione programmata, novità del sistema, avviso a un singolo utente ("il tuo scraper X è sospeso, parliamone").

## Le due categorie di notifica

Le notifiche hanno **due categorie**, e per ora solo due:

| Categoria | Origine | Tipi (`kind`) |
|---|---|---|
| **Sistema** | generate dal motore (alert engine, summary, messaggi testuali del core) | `alert_digest`, `summary`, `system_message` |
| **Admin** | scritte da un amministratore | `admin_message` |

I messaggi testuali — admin (`admin_message`) e di sistema (`system_message`) — condividono lo **stesso payload** (titolo + body) e la stessa pipeline di render: il body è **Markdown** ([alert-event](../../4-capabilities/contracts/alert-event.md), AEV-R7), reso da ogni canale tramite gli helper del core. Una sola macchina di formattazione per tutto ciò che è testo.

La categoria è il taglio che l'utente vede nello storico: le notifiche admin hanno **icona e colore dedicati** per essere immediatamente riconoscibili, e lo storico è filtrabile per categoria.

## Come viaggia il messaggio

Il messaggio admin **riusa la pipeline delle notifiche** ([notification-architecture](../../2-architecture/notification-architecture.md)): per ogni destinatario viene scritta una riga nello storico interno e tentata la consegna su ogni canale che **quell'utente** ha abilitato. Nessun canale nuovo, nessuna logica speciale.

```mermaid
flowchart TD
    A[Admin: titolo + testo<br/>destinatario: tutti / utente] --> M[(admin_message)]
    M --> U{Per ogni destinatario}
    U --> LOG[(Storico interno<br/>scritto SEMPRE, non letto)]
    U --> CH{Canali abilitati<br/>dall'utente}
    CH -- ">=1" --> N[Consegna sui notifier<br/>esito per canale]
    CH -- nessuno --> ONLY[Solo storico in-app:<br/>il messaggio non si perde]
```

La garanzia chiave è ereditata dal design esistente (ALERT-R13: storico scritto **sempre**): un utente con **tutti i notifier disattivati riceve comunque il messaggio** nella pagina delle notifiche ricevute, con badge non letto. I notifier restano canali di consegna aggiuntivi.

## Requisiti

- **ADMSG-R1** — L'admin dispone di una pagina per comporre un messaggio (**titolo + testo in Markdown**) e inviarlo a **tutti gli utenti attivi** o a **un utente specifico**. L'editor è una textbox con **anteprima live** del render, così quel che l'admin vede è quel che i canali HTML consegnano.
- **ADMSG-R2** — Per ogni destinatario il messaggio è registrato nello **storico interno** (categoria admin, stato non letto) — **sempre**, anche senza canali configurati — e consegnato su **tutti i canali abilitati** dal destinatario, con esito per canale (stessa semantica di ALERT-R13/R14).
- **ADMSG-R3** — Nello storico dell'utente la notifica admin è **visivamente distinta** (icona e colore dedicati alla categoria) e lo storico è filtrabile per categoria.
- **ADMSG-R4** — Le categorie sono due: **sistema** (`alert_digest`, `summary`, `system_message`) e **admin** (`admin_message`). Il `kind` determina la categoria; i messaggi testuali hanno payload piatto (titolo + body Markdown, niente struttura a carrelli) e ogni canale li rende con gli helper del core (NOT-R8: degradazione, mai fallimento).
- **ADMSG-R5** — L'admin vede l'elenco dei messaggi **che ha inviato** con gli **esiti di consegna** per destinatario e canale (consegnata / fallita / solo in-app). Non vede lo stato letto/non letto degli utenti né il resto del loro storico.
- **ADMSG-R6** — Il messaggio inviato è **immutabile** (niente modifica o richiamo); un errore si corregge inviando un nuovo messaggio. La purge globale per data ([manutenzione](system-logs-and-maintenance.md)) si applica anche alle notifiche admin.

## Interazione con i poteri di governo dei canali

L'admin **abilita o disabilita ogni notifier per tutti gli utenti** a runtime ([plugin-configuration](plugin-configuration.md), PCFG-R8) — speculare alla sospensione globale di uno scraper (SCHED-R2). Un canale disabilitato globalmente non consegna nulla, nemmeno i messaggi admin: in quel caso vale la garanzia dello storico in-app.
