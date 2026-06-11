# Email — Notifier

> **Implemented plugin** · Tipo: notifier · Stato: primo notifier previsto. Contratto generico: [notifier-plugin](../../3-features/plugins/notifier-plugin.md) · Guida: [notifier-development-guide](../../plugin-development/notifier-development-guide.md).

## Cosa fa

Consegna digest e summary via **email (SMTP)**. È il canale di riferimento: funziona con qualunque casella, non richiede account su piattaforme terze.

## Configurazione

| Livello | Campi | Note |
|---|---|---|
| **Admin** (sistema) | `smtp_host`, `smtp_port` (default 587), `smtp_user`, `smtp_password` (secret), `use_tls` (default true), `from_address` | Nel DB via UI admin; finché incompleta il canale è "non disponibile" per tutti |
| **Utente** | `to_address` (email, required) + flag attivo | Dal Profilo, con bottone Test |

## Formattazione

- **Digest** (`alert_digest`): oggetto sintetico ("Watch 'Em All — N carrelli con novità"); corpo HTML con una sezione per carrello: badge degli eventi, tabella prodotti con provenienza (icona/nome scraper), prezzo prima → dopo, sconto, link; totali e barra soglia. Fallback text/plain.
- **Summary** (`summary`): oggetto "Riepilogo periodico"; corpo con lo stato di tutti i carrelli.
- Lingua: dai file `backend/locales/{it,en}.json` del plugin, secondo la lingua dell'utente.

## Errori e retry

SMTP non raggiungibile / autenticazione fallita: 3 tentativi con backoff, poi `NotifierDeliveryError` descrittivo → esito `failed` nello storico dell'utente e warning nel log admin. Indirizzo rifiutato dal server (permanente): nessun retry, errore immediato.

## Dettagli implementativi

| Aspetto | Scelta |
|---|---|
| Invio | `smtplib` standard library (STARTTLS su 587 di default); niente dipendenze esterne |
| Template | rendering HTML semplice lato plugin (no engine pesanti); inline CSS per compatibilità client |
| `send_test` | invia un'email di prova con dati fittizi marcati come tali |
| Tabelle proprie | nessuna (config persistita dal core) |

## Punti aperti

| ID | Punto |
|---|---|
| EML-Q1 | Allegare/incorporare le immagini prodotto o solo link? (default proposto: solo link, niente immagini remote nelle email) |
| EML-Q2 | Limite di prodotti per carrello nel corpo email prima di troncare con "e altri N…" |
