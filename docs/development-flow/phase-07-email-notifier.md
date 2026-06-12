# Fase 7 — Notifiche Email 🎉

> Stato: ☐ da iniziare · Prerequisiti: Fase 6 · [Indice del flusso](README.md)

## Obiettivo

Il primo canale di consegna reale: contratto notifier, configurazione a due livelli con form dinamici, plugin Email, tracking degli esiti per canale. **Chiude la catena del valore**: alla fine di questa fase il prodotto fa il suo mestiere — è la **v0.1**.

## Risultato apprezzabile

L'admin configura l'SMTP dalla sua pagina; l'utente mette il suo indirizzo nel Profilo, preme Test e riceve la prova; alla prossima cadenza con eventi, **il digest arriva in casella**, formattato e leggibile.

## MVP

### Backend

- [ ] **7.B1 — Contratto NotifierPlugin + dispatch minimo** (~1h): interfaccia `NotifierPlugin`, dispatch dai canali attivi, `skipped_no_notifier` quando non ce ne sono ([notifier-plugin](../3-features/plugins/notifier-plugin.md), [dispatch](../4-capabilities/core/alert-engine.md#consegna-ai-canali)). *Verifica: senza canali → `skipped_no_notifier` nello storico.*
- [ ] **7.B2 — Esiti per canale** (~1h): `alert_delivery` (delivered/failed/skipped), merge config filtrato sullo schema utente. *Verifica: canale che fallisce → esito `failed` registrato, digest comunque nello storico.*
- [ ] **7.B3 — API config a due livelli** (~1h): endpoint admin/user dei notifier su `notifier_admin_config` (whitelist chiavi per schema, `is_set` dei secret) ([endpoints](../api/endpoints.md#notifier-utente--profile-and-notifiers)). *Verifica: chiave admin iniettata dall'utente → scartata.*
- [ ] **7.B4 — Flag enabled per-utente + send_test** (~1h): attivazione personale del canale, invio di prova. *Verifica: test da Swagger → consegna di prova sul canale.*
- [ ] **7.B5 — Email: invio SMTP** (~1h): smtplib con STARTTLS, config admin (host/porta/credenziali) ([email](../implemented-plugins/notifiers/email.md)). **Mock**: corpo in solo testo minimale; il digest vero arriva con 7.B6. *Verifica: email reale ricevuta.*
- [ ] **7.B6 — Email: digest HTML + fallback testo** (~1h): template con prezzi/provenienza/soglia, stringhe dietro chiavi i18n (V1: solo `en.json`). *Verifica: email leggibile su un client comune, fallback testo presente.*
- [ ] **7.B7 — Email: retry e errori** (~1h): retry con backoff → `NotifierDeliveryError` tracciata. *Verifica: SMTP irraggiungibile → retry, poi `failed` con motivo.*

### Frontend

- [ ] **7.F1 — Form dinamico: campi base** (~1h): rendering da [ConfigField](../4-capabilities/contracts/config-field.md) (testo/numero/bool, label_key tradotte, default tipizzati) — **un componente unico** del design system. *Verifica: il form si genera da uno schema qualunque.*
- [ ] **7.F2 — Form dinamico: secret** (~1h): campi secret mascherati write-only con indicatore `is_set`. *Verifica: secret salvato → mai rivisibile, `is_set` mostrato.*
- [ ] **7.F3 — UI canali nel Profilo** (~1h): elenco canali con stato composito, form personale + flag attivo + bottone Test ([profile-and-notifiers](../3-features/user/profile-and-notifiers.md)). *Verifica: senza config admin il canale è "non disponibile" per l'utente.*
- [ ] **7.F4 — Pagina admin del notifier + banner** (~1h): config di sistema + test; banner dashboard "nessun notifier attivo". *Verifica: config admin salvata → canale disponibile; banner sparisce all'attivazione.*
- [ ] **7.F5 — Esiti di consegna visibili** (~1h): esiti per canale nel dettaglio dello storico alert. *Verifica: SMTP sbagliato → esito `failed` con motivo, visibile all'utente.*

## Definition of Done

- [ ] 🎉 **v0.1**: lo scenario UC-1/UC-2 gira per intero senza toccare nulla — scrape automatico → soglia raggiunta → email in casella.
- [ ] Un canale rotto non perde nulla: digest nello storico, esito failed tracciato, warning nei log admin.
- [ ] Nessuna riga di codice email nel core: tutto nel plugin, dietro il contratto.
- [ ] [docs-eng](../../docs-eng/) aggiornata in inglese con la sola parte implementata in questa fase (DOC-12).

## Riferimenti

[notification-architecture](../2-architecture/notification-architecture.md) · [notifier-development-guide](../plugin-development/notifier-development-guide.md)
