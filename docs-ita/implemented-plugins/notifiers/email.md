# Email — Notifier

> **Implemented plugin** · Tipo: notifier · Stato: primo notifier previsto. Contratto generico: [notifier-plugin](../../3-features/plugins/notifier-plugin.md) · Guida: [notifier-development-guide](../../plugin-development/notifier-development-guide.md).

## Cosa fa

Consegna digest e summary via **email (SMTP)**. È il canale di riferimento: funziona con qualunque casella, non richiede account su piattaforme terze.

## Configurazione

| Livello | Campi | Note |
|---|---|---|
| **Admin** (sistema) | `smtp_host`, `smtp_port` (default 587), `smtp_user`, `smtp_password` (secret), `use_tls` (default true), `from_address` | Nel DB via UI admin; finché incompleta il canale è "non disponibile" per tutti |
| **Utente** | solo il flag attivo | Dal Profilo. Da 10.B25 il canale **non dichiara campi utente**: il destinatario è l'indirizzo dell'account (`contact_email`, altrimenti l'username, che da 10.B23 *è* un indirizzo), iniettato dal core come `account_email`. Un solo posto dove una persona si raggiunge, quindi nessun secondo campo che possa contraddire il primo. Su un account nuovo il canale nasce acceso. |

## Formattazione

- **Digest** (`alert_digest`): oggetto sintetico ("Watch 'Em All — N carrelli con novità"); corpo HTML con una sezione per carrello: badge degli eventi, tabella prodotti con provenienza (icona/nome scraper), prezzo prima → dopo, **differenza**, link; totali e barra soglia. Fallback text/plain.
  La colonna **differenza** è la variazione percentuale con segno fra i due prezzi della riga (positiva se il prezzo è salito, negativa se è sceso, colorata di conseguenza; trattino se non c'è un prezzo precedente con cui confrontarla). **Non** è lo `discount_pct` del prodotto, che è lo sconto sul prezzo di listino: la colonna mostrava quello con un meno cablato, quindi un prodotto uscito dalla promozione e **salito** di prezzo veniva riportato come `-0%` ([#37](https://github.com/caporalesimone/watch-em-all/issues/37)).
- **Summary** (`summary`): oggetto "Riepilogo periodico"; corpo con lo stato di tutti i carrelli.
- Lingua: dai file `backend/i18n/` del plugin (V1: solo `en.json`), secondo la lingua dell'utente, con fallback su `en`.

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
