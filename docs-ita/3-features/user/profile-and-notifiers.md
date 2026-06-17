# Profilo e configurazione notifier (lato utente)

> **Layer 3 — Feature utente** · Audience: architetti, developer · Testo + Mermaid, niente codice.

## Scopo

La pagina Profilo concentra tutto ciò che riguarda l'account e la consegna delle notifiche: lingua, password, cadenza alert, report periodico e canali di notifica personali. I notifier stanno qui (non nella barra di navigazione) per alleggerire la nav.

## Requisiti

### Account
- **PROF-R1** — Cambio password (vecchia + nuova, requisiti minimi di lunghezza); il cambio invalida tutte le sessioni attive.
- **PROF-R2** — Scelta della **lingua** dell'interfaccia, persistita sul profilo: usata dalla UI a ogni login e dal core per generare il testo delle **notifiche**. Default di sistema per i nuovi utenti. **V1 English-only**: `locale` fisso a `en`, selettore non esposto; l'impianto (campo, chiavi, risoluzione per-utente) resta attivo per il [multilingua futuro](../../future-improvements/platform.md).
- **PROF-R3** — Il tema (chiaro/scuro) è una preferenza **di browser** (non di account), ricordata localmente; default scuro. Scelta dichiarata: il tema è estetica del dispositivo, la lingua è identità dell'utente.

### Notifiche
- **PROF-R4** — Cadenza alert: picker dei giorni della settimana + orario ([dettagli](alerts-and-notifications.md)).
- **PROF-R5** — Report periodico: on/off, frequenza, giorno, orario ([dettagli](summary-report.md)).

### I miei dati
- **PROF-R11** — Sezione "I miei dati": esportazione self-service di tutti i propri dati in JSON o CSV ([dettagli](data-export.md)).

### Canali (notifier)
- **PROF-R6** — La pagina elenca **tutti i notifier abilitati nel sistema**; per ciascuno l'utente vede: stato di configurazione di sistema (se l'admin non ha configurato la sua parte, il canale è mostrato come "non disponibile"), il **form dei propri campi personali** (generato dallo schema dichiarato dal plugin) e un flag **attivo/non attivo**.
- **PROF-R7** — Un canale consegna solo se: abilitato nel sistema (manifest) **e** configurato dall'admin **e** configurato dall'utente (campi obbligatori validi) **e** attivato dall'utente. Lo stato composito è mostrato chiaramente.
- **PROF-R8** — Ogni canale ha un bottone **Test**: invia una notifica di prova con la configurazione corrente (merge sistema+utente) e mostra l'esito. Nessuna persistenza del test.
- **PROF-R9** — I campi segreti sono mascherati e write-only (mai rispediti al client); un valore già impostato è indicato senza rivelarlo.
- **PROF-R10** — Disattivare un canale **non** ne cancella la configurazione (si può riattivare senza reinserire i dati).

## Stato composito di un canale

```mermaid
stateDiagram-v2
    [*] --> NonDisponibile: manca la config di sistema (admin)
    NonDisponibile --> Configurabile: l'admin completa la sua parte
    Configurabile --> Pronto: l'utente compila i campi obbligatori
    Pronto --> Attivo: l'utente attiva il canale
    Attivo --> Pronto: disattivazione (config conservata)
    Attivo --> Attivo: test di invio
```

## Banner di dashboard

Finché l'utente non ha **alcun canale attivo**, la dashboard mostra un banner informativo: *"Nessun notifier configurato — non riceverai notifiche (le trovi nello Storico alert)"*. Nessuna funzionalità è bloccata: lo storico interno è sempre la fonte primaria.
