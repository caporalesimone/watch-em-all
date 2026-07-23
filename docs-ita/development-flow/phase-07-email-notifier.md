# Fase 7 — Notifiche Email 🎉

> Stato: 🚧 MVP implementati (2026-07-23), in attesa di release `0.7.0` · Prerequisiti: Fase 6 · [Indice del flusso](README.md)

> **Decisioni prese in implementazione (2026-07-23):**
> - **In-app = canale a pieno titolo** (`InAppNotifier`), mostrato nella lista canali del Profilo: **l'utente NON può disattivarlo** (sempre attivo), consegna **inline** al digest (non drenata); **solo l'admin** può spegnerlo globalmente (kill-switch). Unifica il dispatch e conserva l'invariante di fase 6 salvo intervento admin. *(Questo estende la spec di fase 6 → riconciliazione nei doc architettura/feature.)*
> - **Toggle admin per-notifier (kill-switch, PCFG-R8) portato in fase 7** (era rinviato a fase 10): serve a governare l'in-app, che non ha gate di config. La governance admin più ampia (categorie/messaggi/cleanup) resta fase 10.
> - **Consegna canali di rete asincrona**: passo periodico dedicato nel worker (`drain_deliveries`), disaccoppiato dallo scrape; best-effort (retry/backoff nel plugin, nessun re-drain dei `failed`). **Analisi + hardening della consegna rinviati alle fasi finali** (blackout SMTP oltre il tick, eventuale re-drain bounded, throttling a 50-100 utenti).
> - **Contenuto email**: solo link (niente immagini remote), nessun troncamento per ora (EML-Q1/Q2 riviste su digest reale; default confermati).
> - **Dev tooling**: **Mailpit** in `compose-dev.yml` (SMTP 1025 / UI 8025) per testare le email; voce **Debug** in fondo alla sidebar (user+admin) coi link ai tool, temporanea (da rimuovere prima della v1).

## Obiettivo

Il primo canale di consegna reale: contratto notifier, configurazione a due livelli con form dinamici, plugin Email, tracking degli esiti per canale. **Chiude la catena del valore**: alla fine di questa fase il prodotto fa il suo mestiere — è la **0.1**.

## Risultato apprezzabile

L'admin configura l'SMTP dalla sua pagina; l'utente mette il suo indirizzo nel Profilo, preme Test e riceve la prova; appena uno scrape produce eventi, **il digest arriva in casella**, formattato e leggibile.

## 📌 Reminder — consegna ASINCRONA (deciso ragionando in fase 6, 2026-07-22)

> **Contesto della decisione.** In fase 6 la **cadenza a orario è stata rimossa**: gli alert sono **event-driven**, il motore gira **a fine scrape** (schedulato + scrape-now + "Simula scraping" del TP) e produce **un digest aggregato per utente per run di scrape**, scritto **sempre** in `alert_log`. Ragionando sullo scenario "50–100 utenti, uno scrape automatico ne notifica 15" abbiamo separato due cose: **calcolare/scrivere il digest** (economico, nessuna coda — `alert_log` è già la parte durevole) e **consegnarlo sui canali** (lento, può fallire).
>
> **Decisione per la fase 7:** la consegna sui canali è **asincrona / disaccoppiata**, NON inline dentro il run di scrape. Quando il digest è scritto, si creano le righe **`alert_delivery` in stato `pending`** (una per canale attivo); un **passo separato del worker le drena** (invio + retry/backoff, poi `delivered`/`failed`). Motivi: a 50–100 utenti un singolo scrape può generare molti invii SMTP; farli inline bloccherebbe il worker (mono-thread, seriale) e mangerebbe il timeout del run; un SMTP appeso inchioderebbe tutto. È **best-effort** (coerente con la doc: lo storico interno è la fonte primaria; un invio fallito non si ritenta all'infinito, il prossimo digest porta il nuovo stato). Riusa la tabella **`alert_delivery` già a piano** → niente broker/coda pesante né dead-letter (si resta nello spirito "niente code asincrone" della doc, con una coda-leggera solo perché il volume degli invii può avere picchi).
>
> **Impatto sugli MVP sotto:** 7.B1/7.B2 vanno implementati col modello **pending → drain** (scrivi `alert_delivery` pending alla scrittura del digest; il worker scoda e aggiorna gli esiti), non con invio sincrono dentro il motore alert.

## ⚠️ Da discutere PRIMA di iniziare — design system condiviso dei plugin

La Fase 7 introduce il **primo notifier** ed è il **primo caso multi-plugin della stessa famiglia** (sono previsti **2-3 notifier**). È il momento giusto per decidere *come* i plugin condividono la UI **prima** di scrivere tre notifier che divergono. L'astrazione vera resta rimandata (con un solo scraper sarebbe prematura, [discussione 0.3.4]), ma le scelte qui sotto vanno fissate ora per **non obbligare un refactor importante** dopo. Vincoli già vigenti: [FE-8/FE-13/FE-16/FE-17/FE-18](../../docs/developer-rules/frontend/rules.md) (riuso in `$lib/components`, "un pattern usato due volte si estrae", i plugin **devono** usare il design system, widget condivisi self-contained/props-driven), [SCR-R12](../../docs/3-features/plugins/scraper-plugin.md) (tabella dry-run condivisa) e 7.F1 (form di config = "componente unico del DS").

**Argomenti di discussione:**

1. **Modello di condivisione** — libreria (`import` da `$lib/components`) vs **host-injection** (l'app monta il widget intorno alla pagina del plugin) vs ibrido. Quali widget sono primitive importate e quali iniettati dall'host?
2. **Inventario widget per i notifier** — quali nascono già con l'email e vanno condivisi (non inline): **form di config dinamico** (7.F1/7.F2, inclusi i campi secret), **bottone Test/Send**, **esiti di consegna** (tabella), **banner "nessun notifier attivo"** (7.F4), **chip di stato canale**, popup/overlay.
3. **Overlay/popup** — modal (bloccante, per le conferme) vs toast (esiti, non bloccante); ancoraggio **top-center**; **portal unico** alla radice dell'app-shell per garantire lo z-index "sopra tutto".
4. **i18n dei widget condivisi** — namespace **core** (`ui.*`) vs duplicazione per-plugin; si lega al tool di consistenza i18n ([4.B11](phase-04-worker-scheduling.md)).
5. **Token/tema e varianti** — `<Button variant>` per chiudere i ripetuti fix di hover/fill; dark mode coerente.
6. **Contratto e stabilità** — superficie pubblica del DS in `$lib/components`; quanto è "stabile" l'API su cui i plugin dipendono.
7. **Scope al 1° notifier** — cosa estrarre **subito** con l'email (applicando FE-8 in modo proattivo, dato che 2°/3° notifier arriveranno) vs cosa lasciare al secondo uso.
8. **Lato scraper** — Scrape-now + tabella dry-run: mantenere il seam, estrazione al **2° scraper** (stesso principio); allineamento di dragon_store quando conviene.
9. **Host-injection dello Scrape-now** — come il widget conosce il plugin (`route_base`), dove si renderizza il bottone, stato cooldown/countdown (store core keyed per plugin).

> **Esito atteso:** decidere modello (#1), inventario minimo da estrarre col 1° notifier (#2/#7) e meccanica overlay (#3); il resto (token, host-injection scraper) può seguire. Finché non si decide, il 1° notifier si scrive **self-contained/props-driven** (FE-18) per non precludere nessuna opzione.

## MVP

### Backend

- [x] **7.B1 — Contratto NotifierPlugin + dispatch minimo** (~1h): interfaccia `NotifierPlugin`, dispatch dai canali attivi, `skipped_no_notifier` quando non ce ne sono ([notifier-plugin](../3-features/plugins/notifier-plugin.md), [dispatch](../4-capabilities/core/alert-engine.md#consegna-ai-canali)). *Verifica: senza canali → `skipped_no_notifier` nello storico.*
- [x] **7.B2 — Esiti per canale** (~1h): `alert_delivery` (delivered/failed/skipped), merge config filtrato sullo schema utente. *Verifica: canale che fallisce → esito `failed` registrato, digest comunque nello storico.*
- [x] **7.B3 — API config a due livelli** (~1h): endpoint admin/user dei notifier su `notifier_admin_config` (whitelist chiavi per schema, `is_set` dei secret) ([endpoints](../api/endpoints.md#notifier-utente--profile-and-notifiers)). *Verifica: chiave admin iniettata dall'utente → scartata.*
- [x] **7.B4 — Flag enabled per-utente + send_test** (~1h): attivazione personale del canale, invio di prova. *Verifica: test da Swagger → consegna di prova sul canale.*
- [x] **7.B5 — Email: invio SMTP** (~1h): smtplib con STARTTLS, config admin (host/porta/credenziali) ([email](../implemented-plugins/notifiers/email.md)). **Mock**: corpo in solo testo minimale; il digest vero arriva con 7.B6. *Verifica: email reale ricevuta.*
- [x] **7.B6 — Email: digest HTML + fallback testo** (~1h): template con prezzi/provenienza/soglia, stringhe dietro chiavi i18n (V1: solo `en.json`). *Verifica: email leggibile su un client comune, fallback testo presente.*
- [x] **7.B7 — Email: retry e errori** (~1h): retry con backoff → `NotifierDeliveryError` tracciata. *Verifica: SMTP irraggiungibile → retry, poi `failed` con motivo.*

### Frontend

- [x] **7.F1 — Form dinamico: campi base** (~1h): rendering da [ConfigField](../4-capabilities/contracts/config-field.md) (testo/numero/bool, label_key tradotte, default tipizzati) — **un componente unico** del design system. *Verifica: il form si genera da uno schema qualunque.*
- [x] **7.F2 — Form dinamico: secret** (~1h): campi secret mascherati write-only con indicatore `is_set`. *Verifica: secret salvato → mai rivisibile, `is_set` mostrato.*
- [x] **7.F3 — UI canali nel Profilo** (~1h): elenco canali con stato composito, form personale + flag attivo + bottone Test ([profile-and-notifiers](../3-features/user/profile-and-notifiers.md)). *Verifica: senza config admin il canale è "non disponibile" per l'utente.*
- [x] **7.F4 — Pagina admin del notifier + banner** (~1h): config di sistema + test; banner dashboard "nessun notifier attivo". *Verifica: config admin salvata → canale disponibile; banner sparisce all'attivazione.*
- [x] **7.F5 — Esiti di consegna visibili** (~1h): esiti per canale nel dettaglio dello storico alert. *Verifica: SMTP sbagliato → esito `failed` con motivo, visibile all'utente.*

## Definition of Done

- [x] 🎉 **0.1**: lo scenario UC-1/UC-2 gira per intero senza toccare nulla — scrape automatico → soglia raggiunta → email in casella. *(E2E live validato con Mailpit su stack isolato: price drop → simula scrape → digest → worker drena la coda → email digest ricevuta; esiti `email=delivered`+`in_app=delivered`.)*
- [x] Un canale rotto non perde nulla: digest nello storico, esito failed tracciato, warning nei log admin.
- [x] Nessuna riga di codice email nel core: tutto nel plugin, dietro il contratto.
- [x] [docs](../../docs/) aggiornata in inglese con la sola parte implementata in questa fase (DOC-12).

## Riferimenti

[notification-architecture](../2-architecture/notification-architecture.md) · [notifier-development-guide](../plugin-development/notifier-development-guide.md)
