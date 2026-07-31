# Fase 16 — Custodia dello storico prezzi (governo admin)

> Stato: 💡 idea / da dettagliare · **post-1.0** (oltre il perimetro della [1.0](../1-business/product-overview.md)) · Prerequisiti: Fase 9 (storico per prodotto), Fase 10 (plancia admin) · [Indice del flusso](README.md)
>
> **Annotata il 2026-07-31**, come conseguenza diretta di una decisione di Simone durante il code review della Fase 9: *"il prezzo storico di un prodotto deve valere cross utente… mai cancellare gli storici dei prodotti. Lasciare all'admin in fase 16 la gestione di questi dati storici."* Gli MVP qui sotto sono abbozzati e vanno dettagliati (analisi → proposta → ok) prima di diventare lavoro reale.

## Obiettivo

Dare all'**admin** — e a nessun altro — gli strumenti per guardare e potare `price_history`, la tabella che per scelta di progetto non si cancella mai da sé.

## Perché esiste questa fase

In fase 9 lo storico prezzi ha smesso di appartenere alla riga di catalogo di un utente ed è stato riancorato all'**identità del prodotto** `(plugin_id, external_id)` (CATSVC-R4). La conseguenza voluta è che lo storico **sopravvive a tutto**: a chi smette di seguire un prodotto, alla cancellazione della riga dal catalogo, alla cancellazione dell'utente. Chi inizia a seguire un prodotto domani eredita la storia che qualcun altro ha raccolto, e basta **un** osservatore perché quella catena resti fresca per tutti.

Il rovescio è che nessun meccanismo la rimpicciolisce. Nasce quindi una categoria di dati nuova per questo progetto: **conoscenza senza proprietario** — catene che nessun utente referenzia più, perché il prodotto non è nel catalogo di nessuno. Sono esattamente i dati che valgono di più (un nuovo osservatore li eredita) e che nessuno reclamerebbe se sparissero. Decidere il loro destino è un atto di **governo**, non una pulizia: per questo sta con gli strumenti dell'admin e non fra le azioni dell'utente.

**La regola da non violare:** la potatura è sempre **esplicita e dell'admin**. La retention automatica di questo progetto (`log_retention_days`, MNT-R2) pota dati **operativi** — log e record di run — e la pagina delle impostazioni promette all'admin che *"lo storico prezzi non si pota mai"*. Estendere quella retention allo storico romperebbe la promessa in silenzio e, cosa peggiore, cancellerebbe conoscenza che appartiene a più utenti insieme per una scelta fatta da uno.

## Risultato apprezzabile

L'admin apre la sua pagina e vede quanto pesa lo storico, quante catene non sono referenziate da nessuno e da quanto tempo. Decide, con un criterio dichiarato e una conferma che dice esattamente cosa sta per andare, di potare quelle inattive da oltre un anno. Nessun utente perde il grafico di un prodotto che sta seguendo.

## Il punto architetturale

**"Non referenziata" è una domanda che il modello sa già rispondere**, ed è quello che rende questa fase piccola: una catena è orfana quando nessuna riga di `products` ha la sua coppia `(plugin_id, external_id)`. È un `NOT EXISTS`, non un contatore da mantenere — quindi non serve nessuna colonna nuova e nessuna bookkeeping che possa andare fuori sincrono.

**Il rischio vero non è tecnico, è di lettura.** Una catena orfana *oggi* può tornare referenziata domani, appena un utente aggiunge quel prodotto. Quindi "orfana" da sola non basta come criterio: serve accoppiarla a **da quanto** (l'ultima voce, non la prima), o si pota la storia di un prodotto che qualcuno stava per iniziare a seguire.

## MVP (abbozzati)

### Backend

- [ ] **16.B1 — Inventario dello storico** (~1h): quante voci, quante catene distinte, quante **non referenziate** da nessuna riga di catalogo, quanto pesa la tabella, e la data dell'ultima voce di ciascuna catena. Sola lettura, per admin. *Verifica: i numeri corrispondono a query fatte a mano sul DB.*
- [ ] **16.B2 — Potatura esplicita a criterio** (~1h): rimozione delle catene **orfane e inattive da più di N** (N scelto dall'admin, mai un default che agisce da solo). Restituisce quante catene e quante voci sono andate. Mai una potatura che tocchi una catena referenziata da un catalogo, nemmeno su richiesta: quella non è una decisione dell'admin, è il grafico di un utente. *Verifica: una catena referenziata sopravvive a qualunque criterio; una orfana e vecchia va; una orfana e recente resta.*
- [ ] **16.B3 — Anteprima prima di agire** (~30m): lo stesso criterio in sola lettura, per dire "questo pota 412 catene e 9.310 voci" **prima** del click. Vale la regola già applicata alle pulizie del catalogo (9.F4/CAT-R10): un numero, non una descrizione. *Verifica: l'anteprima e l'esecuzione riportano lo stesso numero.*
- [ ] **16.B4 — Tracciare la potatura** (~30m): una potatura è irreversibile e riguarda dati di più utenti, quindi va nel `system_log` con criterio e conteggi. *Verifica: la riga di log basta a ricostruire cosa è stato fatto e con che criterio.*

### Frontend

- [ ] **16.F1 — Sezione nella plancia admin** (~1h): l'inventario, il criterio, l'anteprima e la conferma. La conferma dichiara che l'operazione è irreversibile e che riguarda dati **condivisi**. *Verifica: nessuna azione raggiungibile senza anteprima.*

## Da decidere prima di iniziare

- **Il criterio**: "orfana da più di N mesi" (proposta) è il più difendibile, ma va deciso se N è un'impostazione salvata o un parametro dell'operazione — con la preferenza per **parametro**, perché un'impostazione salvata invita ad automatizzarla, che è ciò che questa fase esclude.
- **Export prima di potare?** Una potatura irreversibile su conoscenza condivisa suggerisce un export; l'export è però materia della [fase 11](phase-11-insights.md), quindi va deciso se questa fase lo richiede come prerequisito o se ne fa a meno.
- **Cosa vede l'admin di una catena orfana**: solo i numeri, o anche nome e URL del prodotto? Un URL non serve a decidere e apre la domanda su cosa l'admin possa leggere dei dati di navigazione degli utenti.
- **Un limite di crescita esiste?** Va stimato quanto cresce `price_history` in un anno d'uso reale prima di decidere se questa fase è manutenzione utile o ottimizzazione prematura. Solo cambi di prezzo, mai campionamenti (CATSVC-R4), quindi la crescita è probabilmente lenta — ma è un'ipotesi, non un dato.

## Definition of Done

- [ ] L'admin vede quanto storico c'è e quanta parte non è referenziata da nessuno.
- [ ] Una potatura richiede un criterio esplicito e mostra il suo effetto prima di agire.
- [ ] Una catena referenziata da un catalogo **non si pota in nessun caso**.
- [ ] Nessuna potatura automatica esiste, e la promessa fatta all'admin nelle impostazioni resta vera.
- [ ] [docs](../../docs/) aggiornata in inglese con la sola parte implementata (DOC-12).

## Riferimenti

[Fase 9 — Dragon Store completo](phase-09-dragonstore-complete.md) · [Fase 10 — Governo admin](phase-10-admin-governance.md) · [Fase 11 — Summary, analisi prezzi, export](phase-11-insights.md) · [price history](../../docs/4-capabilities/core/price-history.md) · [catalog update service](../../docs/4-capabilities/core/catalog-update-service.md) · [schema del database](../../docs/4-capabilities/database/schema.md)
