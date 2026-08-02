# L'esperienza dell'amministratore — parti ancora da realizzare

> **Layer 1 — Business / UX** · Audience: tutti · Solo testo descrittivo.
>
> La parte **già realizzata** (primo avvio, creazione utenti con crea+lista, governo degli scraper, registro di sistema, manutenzione e impostazioni globali, il confine di privacy) è stata migrata nella wiki inglese canonica: [`docs/1-business/admin-experience.md`](../../docs/1-business/admin-experience.md). Qui restano **solo le esperienze che dipendono da capacità non ancora costruite** (fase 6+). I dettagli funzionali sono nel [Layer 3 — feature admin](../3-features/admin/).

## Gestione avanzata degli utenti

Oltre a crearli ed elencarli (già realizzato), l'admin potrà disabilitare un account (con effetto immediato sulle sessioni) o reimpostarne la password. La lista mostrerà anche filtri rapidi che separano con un click gli account **attivi**, **disabilitati** e **in cancellazione**, e l'ordinamento per ultimo accesso.

La **cancellazione è differita**, come un cestino con la data di svuotamento: "cancella" disattiva l'account, lo marca **in cancellazione** e fissa una **scadenza** (per default 30 giorni dopo, l'admin può cambiare la durata del periodo). Nessun dato viene perso in questa fase, e finché la scadenza non arriva un tasto **annulla la cancellazione** — l'account torna disabilitato (mai direttamente attivo), e disabilitato può restare per sempre: non c'è alcuna scadenza sugli account disabilitati. La perdita vera avviene **automaticamente**: una volta al giorno il sistema elimina gli account la cui scadenza è passata. A quel punto viene eliminato **tutto**: prima ogni plugin cancella i propri dati di quell'utente, poi il sistema elimina quelli centrali — cataloghi, carrelli, storici, recapiti dei canali. Su un account già marcato l'admin può anche rinunciare all'attesa e **cancellarlo subito**: è la stessa distruzione, con un altro innesco. Resta però un secondo passo e non il primo — un solo click che distrugge un account annullerebbe la finestra reversibile per tutti, non solo per chi lo preme apposta.

L'utente è avvisato quando viene disabilitato, quando viene marcato per la cancellazione — con la data in cui sparirà — e quando viene cancellato davvero. Queste tre notizie **arrivano per mail comunque**, anche a chi ha spento le notifiche email: quell'interruttore governa gli avvisi che uno ha chiesto di ricevere, e la copia in-app di *"il tuo account è disabilitato"* si leggerebbe solo accedendo, cioè facendo la cosa che quel messaggio dice essere diventata impossibile. Se un utente disabilitato o in cancellazione prova a entrare, il sistema gli dice che l'accesso non è più possibile e di contattare l'amministratore.

## Sorvegliare il lavoro — statistiche degli scraper

Oltre al registro di sistema (già realizzato), l'admin avrà bisogno di sapere **quanto lavorano** gli scraper e **se stanno bene**. La sua plancia offrirà:

- per ogni scraper, l'esito dell'**ultima esecuzione** (durata reale, prodotti trovati, novità, variazioni di prezzo, prodotti spariti, errori) e l'**andamento nel tempo** delle esecuzioni — quante al giorno, quanto durano, quante richieste fanno ai siti;
- il dettaglio di ogni esecuzione, **utente per utente**, per capire chi genera il carico.

## Misurare il carico

Accanto alla salute degli scraper, l'admin avrà una **dashboard con i numeri dell'installazione**: quanti prodotti e carrelli esistono in totale, quali utenti hanno caricato più dati, quanto carico genera ciascun utente su ogni scraper (richieste verso i siti, tempi di lavorazione), e quante notifiche escono dal sistema — in totale, per utente e per canale, con le medie del periodo.

Sono sempre e soltanto numeri: la dashboard dice che un utente ha trecento prodotti e quattro carrelli, **mai quali**. Serve a capire chi e cosa fa lavorare il sistema, e a regolare di conseguenza orari, limiti e — quando serve — una conversazione con l'utente dalla configurazione esagerata.

## Configurare i canali di notifica

I canali di consegna (email, Discord…) hanno due livelli di configurazione: l'admin imposta la parte **di sistema** (ad esempio il server di posta in uscita e le sue credenziali), ogni utente aggiunge la propria parte **personale** (il proprio indirizzo). Senza la parte di sistema il canale non è utilizzabile da nessuno; l'interfaccia lo segnala.

Come per gli scraper, l'admin ha anche l'**interruttore globale**: può disabilitare un canale **per tutti gli utenti** (e riattivarlo) senza toccare le configurazioni personali, che restano al loro posto in attesa della riattivazione.

## Comunicare con gli utenti

L'admin può scrivere direttamente agli utenti attraverso il sistema stesso: una pagina dedicata gli permette di comporre un messaggio (titolo e testo) e inviarlo **a tutti** o **a un utente specifico** — un avviso di manutenzione, una novità, una segnalazione personale. Il messaggio viaggia sui canali di notifica che ciascun utente ha attivato; chi non ha alcun canale lo trova comunque **nella pagina delle notifiche ricevute**, dove i messaggi dell'admin sono evidenziati con un'icona e un colore propri. L'admin vede gli esiti di consegna dei propri messaggi, non lo stato di lettura.

## Manutenzione — parti da realizzare

- **Pulizia degli storici alert**: l'admin applica regole globali per data ("elimina le notifiche di tutti più vecchie di 90 giorni") senza mai vedere il contenuto delle notifiche degli utenti. *(Richiede l'esistenza delle notifiche, fase 6+.)*
