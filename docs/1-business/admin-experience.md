# L'esperienza dell'amministratore

> **Layer 1 — Business / UX** · Audience: tutti · Solo testo descrittivo.

Il racconto dell'esperienza di chi governa l'installazione. I dettagli funzionali sono nel [Layer 3 — feature admin](../3-features/admin/).

## Il primo avvio

L'amministratore installa il sistema (un comando, vedi la documentazione di [infrastruttura](../infrastructure/deployment.md)) e accede con l'account admin creato automaticamente al primo avvio; il sistema gli impone subito il cambio della password temporanea. Da qui in poi la sua casa è l'area di amministrazione.

## Creare gli utenti

Non esiste auto-registrazione: è l'admin a creare ogni account, assegnando username e una password temporanea che l'utente dovrà cambiare al primo accesso. Dalla stessa pagina può disabilitare un account (con effetto immediato sulle sessioni) o reimpostarne la password.

## Governare gli scraper

È la responsabilità più importante. Per ogni scraper installato l'admin decide:

- **Quante volte al giorno e a che ora** lo scraper gira: da una a più esecuzioni quotidiane, ciascuna a un orario scelto. Un negozio con prezzi lampo può girare tre volte al giorno; uno statico, una sola.
- **Quanto lavoro è ammesso in parallelo**: il sistema può eseguire più scraper contemporaneamente (ognuno internamente lavora da solo, con calma, un sito alla volta), ma l'admin fissa il numero massimo di scraper attivi nello stesso momento e il ritmo massimo delle richieste verso i siti. La regola di casa è ferma: **mai martellare un sito** — niente raffiche, niente decine di richieste simultanee.
- **I parametri operativi** di ciascuno scraper (tempi di attesa, identificazione del client, regole di sconto del sito), dalla pagina di configurazione che ogni plugin fornisce.
- L'eventuale **interruttore di emergenza**: uno scraper può essere sospeso senza disinstallarlo.

## Sorvegliare il lavoro

L'admin ha bisogno di sapere **quanto lavorano** gli scraper e **se stanno bene**. La sua plancia offre:

- per ogni scraper, l'esito dell'**ultima esecuzione** (durata reale, prodotti trovati, novità, variazioni di prezzo, prodotti spariti, errori) e l'**andamento nel tempo** delle esecuzioni — quante al giorno, quanto durano, quante richieste fanno ai siti;
- il dettaglio di ogni esecuzione, **utente per utente**, per capire chi genera il carico;
- il **registro di sistema** in tempo quasi reale: esecuzioni, recuperi dopo un fermo, esecuzioni saltate perché la precedente era ancora in corso, errori — con filtri per gravità e per origine;
- un segnale di **vita del motore di pianificazione**: se il componente che orchestra le esecuzioni si ferma, l'admin lo vede subito.

## Misurare il carico

Accanto alla salute degli scraper, l'admin ha una **dashboard con i numeri dell'installazione**: quanti prodotti e carrelli esistono in totale, quali utenti hanno caricato più dati, quanto carico genera ciascun utente su ogni scraper (richieste verso i siti, tempi di lavorazione), e quante notifiche escono dal sistema — in totale, per utente e per canale, con le medie del periodo.

Sono sempre e soltanto numeri: la dashboard dice che un utente ha trecento prodotti e quattro carrelli, **mai quali**. Serve a capire chi e cosa fa lavorare il sistema, e a regolare di conseguenza orari, limiti e — quando serve — una conversazione con l'utente dalla configurazione esagerata.

## Configurare i canali di notifica

I canali di consegna (email, Discord…) hanno due livelli di configurazione: l'admin imposta la parte **di sistema** (ad esempio il server di posta in uscita e le sue credenziali), ogni utente aggiunge la propria parte **personale** (il proprio indirizzo). Senza la parte di sistema il canale non è utilizzabile da nessuno; l'interfaccia lo segnala.

## Manutenzione

- **Pulizia degli storici**: l'admin applica regole globali per data ("elimina le notifiche di tutti più vecchie di 90 giorni") senza mai vedere il contenuto delle notifiche degli utenti.
- **Parametri globali**: limiti di parallelismo, tempo massimo di un'esecuzione, conservazione dei log.
- **Salute del sistema**: un controllo di vita esposto dall'applicazione e lo stato dei contenitori; per l'ispezione diretta dei dati in sviluppo esiste uno strumento dedicato, mai attivo in produzione.

## Cosa l'admin non può fare

Non vede i carrelli, i cataloghi né le notifiche degli utenti: dei loro dati conosce **solo i numeri** (quanti prodotti, quanti carrelli, quante notifiche — la dashboard del carico), mai i contenuti. Configura il sistema, non i contenuti. Se serve aiutare un utente, lo fa guidandolo — non entrando nei suoi dati.
