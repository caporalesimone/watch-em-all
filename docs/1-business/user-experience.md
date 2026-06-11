# L'esperienza dell'utente

> **Layer 1 — Business / UX** · Audience: tutti · Solo testo descrittivo.

Il racconto dell'esperienza, dal primo accesso alla notifica che chiude il cerchio. I dettagli funzionali sono nel [Layer 3 — feature utente](../3-features/user/).

## Il primo accesso

L'utente riceve dall'amministratore le credenziali (username e password temporanea). Al primo accesso il sistema impone il cambio password. (L'interfaccia è in inglese: la scelta della lingua è prevista dall'impianto ma non offerta nella prima versione.) L'interfaccia è una applicazione web moderna, con tema scuro di default (commutabile in chiaro) e una barra di navigazione laterale sempre presente: Dashboard, Product Picker, Carrelli, Storico prezzi, Storico alert, Profilo e — in fondo, in un gruppo a parte — l'elenco dei siti supportati (gli scraper).

La Dashboard accoglie l'utente con lo stato dei suoi carrelli e, finché non ha configurato un canale di notifica, un avviso gentile: *"Nessun notifier configurato — non riceverai notifiche (le trovi comunque nello Storico alert)"*.

## Dire al sistema cosa osservare

L'utente apre la pagina di uno scraper dal gruppo in fondo alla barra laterale. Qui ogni sito ha la propria interfaccia, pensata per quel sito: tipicamente l'utente può sfogliare in anteprima i prodotti (una "prova" che non salva nulla) e poi selezionare cosa monitorare — singoli prodotti, intere categorie, o ciò che il sito consente. Da quel momento, a ogni esecuzione programmata, lo scraper estrae i prodotti scelti e li deposita nel **catalogo personale** dell'utente.

## Costruire i carrelli

Con il catalogo popolato, l'utente crea i carrelli dalla pagina Carrelli: dà un nome e sceglie la modalità — **legata a un singolo sito** (con i totali calcolati come li calcolerebbe quel sito: sconti a soglia, spedizione) oppure **trasversale** (prodotti da siti diversi, anche lo stesso prodotto ripetuto una volta per sito).

Poi apre il **Product Picker**: una tabella del suo catalogo, ordinabile e filtrabile, dove ogni riga mostra foto, titolo, prezzi, sconto e — sempre — **l'icona del sito di provenienza**. Seleziona le righe e le aggiunge al carrello scelto.

Sul carrello imposta infine la **soglia** ("avvisami sotto i 300 €" oppure "quando lo sconto supera il 25%") e i **tipi di avviso**: sconto su un prodotto, prodotto non più disponibile, prodotto tornato disponibile, tutto il carrello in offerta, soglia raggiunta. Finché non attiva almeno un tipo di avviso, il carrello è solo un contenitore silenzioso.

## Ricevere le notifiche

Dal Profilo l'utente decide **quando** essere avvisato: sceglie i giorni della settimana e l'orario (tutti i giorni alle 22, solo il venerdì alle 9, eccetera). A quell'ora il sistema confronta lo stato attuale con l'ultima notifica e, **solo se è cambiato qualcosa**, invia **un unico messaggio aggregato**: per ogni carrello coinvolto, gli eventi accaduti, con i prodotti etichettati (in offerta, di nuovo disponibile…), i prezzi vecchi e nuovi e la provenienza di ogni prodotto.

Sempre dal Profilo configura i **canali**: per ciascun canale disponibile (email, Discord…) inserisce i propri dati personali e può inviarsi una **notifica di prova** per verificare che tutto funzioni. Può attivare più canali insieme, o nessuno: ogni notifica resta comunque nello **Storico alert** dentro l'applicazione, con l'indicazione di lettura.

Chi lo desidera attiva anche il **report periodico**: una fotografia settimanale o mensile di tutti i carrelli, indipendente dagli eventi.

## Capire se è il momento giusto

La pagina **Storico prezzi** mostra l'andamento nel tempo: per ogni prodotto, il grafico del prezzo con i periodi di indisponibilità ben visibili; per ogni carrello, l'andamento del totale. Selettori rapidi (ultima settimana, ultimo mese, tutto) aiutano a giudicare se l'offerta di oggi è un minimo vero.

Il sistema aiuta anche a leggere i numeri: accanto al grafico, le **statistiche** del prodotto (minimo e massimo storico, media recente, quanto spesso è in offerta) e un **indicatore di convenienza** che dice, dati alla mano, se è un buon momento per comprare. Quando un prezzo tocca il **minimo mai registrato**, un badge lo evidenzia ovunque il prodotto compaia — e chi vuole può farsi avvisare proprio di questo, attivando l'avviso "minimo storico" sul carrello.

## Manutenzione del proprio spazio

I prodotti che spariscono dal sito osservato non vengono cancellati: restano nel catalogo, grigiati, finché l'utente non decide di pulirli. Il Product Picker offre la rimozione dei prodotti delistati, la rimozione selettiva e lo svuotamento completo del catalogo; a catalogo vuoto è disponibile uno "Scrape ora" per ripopolarlo subito senza attendere la prossima esecuzione programmata.

Infine, i dati restano dell'utente: dal Profilo può **esportare tutto** — catalogo, storico prezzi, carrelli, notifiche — in formati aperti (JSON o CSV), in qualunque momento e senza chiedere nulla a nessuno.
