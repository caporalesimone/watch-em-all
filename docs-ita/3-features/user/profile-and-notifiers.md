# Profilo — consegna notifiche e notifier (lato utente)

> **Layer 3 — Feature utente** · Audience: architetti, developer · Testo + Mermaid, niente codice.
>
> **Spec-ahead (fasi 6/7/11).** La parte **account** della pagina Profilo (identità in sola lettura, lingua dell'interfaccia, tema, cambio password) è già implementata in fase 1 ed è documentata in inglese: [`docs/3-features/user/profile-and-notifiers.md`](../../../docs/3-features/user/profile-and-notifiers.md). Questo file conserva solo la parte **non ancora implementata**: la **consegna delle notifiche** — report periodico, esportazione dati, e i **canali notifier** personali. (Gli alert sono **event-driven**: non c'è una cadenza da configurare nel Profilo.)

> **Aggiornamento fase 7 (2026-07-23) — l'in-app è un canale.** L'`in-app` è ora un **canale notifier a pieno titolo** mostrato nell'elenco canali del Profilo, con una regola speciale: **l'utente NON può disattivarlo** (sempre attivo per lui) e non ha config personale; **solo l'admin** può disabilitarlo globalmente (kill-switch). Inoltre l'**interruttore admin per-notifier** (PCFG-R8) è stato implementato in fase 7 (non fase 10): un canale disabilitato dall'admin non è visibile all'utente. Il banner di dashboard è rivisto di conseguenza (l'utente ha sempre l'in-app, salvo kill-switch): segnala l'assenza di **canali esterni** attivi. Vedi il mirror inglese implementato in [`docs/3-features/user/profile-and-notifiers.md`](../../../docs/3-features/user/profile-and-notifiers.md).

## Scopo

La pagina Profilo concentra anche tutto ciò che riguarda la consegna delle notifiche: report periodico, esportazione dei propri dati e canali di notifica personali. I notifier stanno qui (non nella barra di navigazione) per alleggerire la nav.

## Requisiti

### Notifiche
- **PROF-R4** — Nessuna cadenza alert nel Profilo: gli alert sono **event-driven** (scattano a fine scrape); i *tipi* di alert si scelgono sulla card del carrello ([dettagli](alerts-and-notifications.md)).
- **PROF-R5** — Report periodico: on/off, frequenza, giorno, orario ([dettagli](summary-report.md)).

### I miei dati
- **PROF-R11** — Sezione "I miei dati": esportazione self-service di tutti i propri dati in JSON o CSV ([dettagli](data-export.md)).

### Canali (notifier)
- **PROF-R6** — La pagina elenca **tutti i notifier abilitati nel sistema**; per ciascuno l'utente vede: stato di configurazione di sistema (se l'admin non ha configurato la sua parte, il canale è mostrato come "non disponibile"), il **form dei propri campi personali** (generato dallo schema dichiarato dal plugin) e un flag **attivo/non attivo**.
- **PROF-R7** — Un canale consegna solo se: abilitato nel sistema (manifest) **e** configurato dall'admin **e** configurato dall'utente (campi obbligatori validi) **e** attivato dall'utente. Lo stato composito è mostrato chiaramente.
- **PROF-R8** — ~~Ogni canale ha un bottone **Test**.~~ **Ritirato in 10.X4.** Aveva senso finché il recapito lo scriveva l'utente in quella pagina; da 10.B23/10.B25 il recapito **è** l'account e si è già dimostrato funzionante portando la password con cui quella persona è entrata. Quel che restava era una sonda sulla configurazione SMTP del server esposta a chi non la può correggere: la prova resta lato admin (NOT-R6).
- **PROF-R9** — I campi segreti sono mascherati e write-only (mai rispediti al client); un valore già impostato è indicato senza rivelarlo.
- **PROF-R10** — Disattivare un canale **non** ne cancella la configurazione (si può riattivare senza reinserire i dati).
- **PROF-R12** (10.F17) — L'**indirizzo di notifica è l'account**. Da 10.B23 l'username *è* un indirizzo email, quindi il profilo lo **mostra** e non offre niente da modificare: cambiare dove arriva la posta vorrebbe dire cambiare con cosa si accede, che è un'operazione dell'admin. L'unica eccezione è l'**admin di bootstrap**, che accede con un nome e non con un indirizzo e quindi imposta il proprio `contact_email` (`PATCH /api/me {contact_email}`, validato e normalizzato a minuscolo); per ogni altro account la risposta è `403 address_not_editable`. Conseguenza sul canale email: **non dichiara più campi utente** (10.B25), quindi nel profilo di quel canale resta l'interruttore — e su un account nuovo è già acceso.

## Stato composito di un canale

```mermaid
stateDiagram-v2
    [*] --> NonDisponibile: manca la config di sistema (admin)
    NonDisponibile --> Configurabile: l'admin completa la sua parte
    Configurabile --> Pronto: l'utente compila i campi obbligatori
    Pronto --> Attivo: l'utente attiva il canale
    Attivo --> Pronto: disattivazione (config conservata)
```

## Banner di dashboard

Finché l'utente non ha **alcun canale attivo**, la dashboard mostra un banner informativo: *"Nessun notifier configurato — non riceverai notifiche (le trovi nello Storico alert)"*. Nessuna funzionalità è bloccata: lo storico interno è sempre la fonte primaria.
