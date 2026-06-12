# Fase 7 — Notifiche Email 🎉

> Stato: ☐ da iniziare · Prerequisiti: Fase 6 · [Indice del flusso](README.md)

## Obiettivo

Il primo canale di consegna reale: contratto notifier, configurazione a due livelli con form dinamici, plugin Email, tracking degli esiti per canale. **Chiude la catena del valore**: alla fine di questa fase il prodotto fa il suo mestiere — è la **v0.1**.

## Risultato apprezzabile

L'admin configura l'SMTP dalla sua pagina; l'utente mette il suo indirizzo nel Profilo, preme Test e riceve la prova; alla prossima cadenza con eventi, **il digest arriva in casella**, formattato e leggibile.

## MVP

### Backend

- [ ] **7.B1 — Contratto notifier + dispatch** (~3h): `NotifierPlugin`, dispatch dai canali attivi con merge filtrato sullo schema utente, `alert_delivery` per-canale (delivered/failed/skipped) ([notifier-plugin](../3-features/plugins/notifier-plugin.md), [dispatch](../4-capabilities/core/alert-engine.md#consegna-ai-canali)). *Verifica: senza canali → `skipped_no_notifier` nello storico.*
- [ ] **7.B2 — API config a due livelli** (~2h): endpoint admin/user dei notifier (whitelist chiavi per schema, `is_set` dei secret), flag `enabled` per-utente, `send_test` ([endpoints](../api/endpoints.md#notifier-utente--profile-and-notifiers)). *Verifica: chiave admin iniettata dall'utente → scartata.*
- [ ] **7.B3 — Plugin Email** (~4h): invio SMTP (smtplib, STARTTLS), digest HTML + fallback testo con prezzi/provenienza/soglia, retry con backoff → `NotifierDeliveryError`, stringhe backend dietro chiavi i18n (V1: solo `en.json`) ([email](../implemented-plugins/notifiers/email.md)). *Verifica: email reale ricevuta e leggibile su un client comune.*

### Frontend

- [ ] **7.F1 — Componente form dinamico** (~3h): rendering da [ConfigField](../4-capabilities/contracts/config-field.md) (label_key tradotte, secret mascherati write-only con indicatore `is_set`, default tipizzati): **un componente unico** del design system. *Verifica: il form si genera da uno schema qualunque.*
- [ ] **7.F2 — UI canali (Profilo + admin)** (~3h): elenco canali con stato composito, form personale + flag attivo + bottone Test; pagina admin del notifier (config di sistema + test); banner dashboard "nessun notifier attivo" ([profile-and-notifiers](../3-features/user/profile-and-notifiers.md)). *Verifica: senza config admin il canale è "non disponibile" per l'utente.*
- [ ] **7.F3 — Esiti di consegna visibili** (~1h): esiti per canale nel dettaglio dello storico alert. *Verifica: SMTP sbagliato → esito `failed` con motivo, visibile all'utente.*

## Definition of Done

- [ ] 🎉 **v0.1**: lo scenario UC-1/UC-2 gira per intero senza toccare nulla — scrape automatico → soglia raggiunta → email in casella.
- [ ] Un canale rotto non perde nulla: digest nello storico, esito failed tracciato, warning nei log admin.
- [ ] Nessuna riga di codice email nel core: tutto nel plugin, dietro il contratto.
- [ ] [docs-eng](../../docs-eng/) aggiornata in inglese con la sola parte implementata in questa fase (DOC-12).

## Riferimenti

[notification-architecture](../2-architecture/notification-architecture.md) · [notifier-development-guide](../plugin-development/notifier-development-guide.md)
