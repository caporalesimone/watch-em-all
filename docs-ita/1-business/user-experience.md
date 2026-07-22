# L'esperienza dell'utente — parti ancora da realizzare

> **Layer 1 — Business / UX** · Audience: tutti · Solo testo descrittivo.
>
> La parte **già realizzata** (primo accesso, dire al sistema cosa osservare, costruire i carrelli) è stata migrata nella wiki inglese canonica: [`docs/1-business/user-experience.md`](../../docs/1-business/user-experience.md). Qui restano **solo le esperienze che dipendono da capacità non ancora costruite** (fase 6+). I dettagli funzionali sono nel [Layer 3 — feature utente](../3-features/user/).

## Ricevere le notifiche

Dal Profilo l'utente decide **quando** essere avvisato: sceglie i giorni della settimana e l'orario (tutti i giorni alle 22, solo il venerdì alle 9, eccetera). A quell'ora il sistema confronta lo stato attuale con l'ultima notifica e, **solo se è cambiato qualcosa**, invia **un unico messaggio aggregato**: per ogni carrello coinvolto, gli eventi accaduti, con i prodotti etichettati (in offerta, di nuovo disponibile…), i prezzi vecchi e nuovi e la provenienza di ogni prodotto.

Sul carrello l'utente sceglie inoltre i **tipi di avviso**: sconto su un prodotto, prodotto non più disponibile, prodotto tornato disponibile, tutto il carrello in offerta, soglia raggiunta. Finché non attiva almeno un tipo di avviso, il carrello è solo un contenitore silenzioso.

Sempre dal Profilo configura i **canali**: per ciascun canale disponibile (email, Discord…) inserisce i propri dati personali e può inviarsi una **notifica di prova** per verificare che tutto funzioni. Può attivare più canali insieme, o nessuno: ogni notifica resta comunque nello **Storico alert** dentro l'applicazione, con l'indicazione di lettura. La Dashboard, finché non c'è un canale configurato, mostra un avviso gentile: *"Nessun notifier configurato — non riceverai notifiche (le trovi comunque nello Storico alert)"*.

Chi lo desidera attiva anche il **report periodico**: una fotografia settimanale o mensile di tutti i carrelli, indipendente dagli eventi.

## Capire se è il momento giusto

La pagina **Storico prezzi** mostra l'andamento nel tempo: per ogni prodotto, il grafico del prezzo con i periodi di indisponibilità ben visibili; per ogni carrello, l'andamento del totale. Selettori rapidi (ultima settimana, ultimo mese, tutto) aiutano a giudicare se l'offerta di oggi è un minimo vero.

Il sistema aiuta anche a leggere i numeri: accanto al grafico, le **statistiche** del prodotto (minimo e massimo storico, media recente, quanto spesso è in offerta) e un **indicatore di convenienza** che dice, dati alla mano, se è un buon momento per comprare. Quando un prezzo tocca il **minimo mai registrato**, un badge lo evidenzia ovunque il prodotto compaia — e chi vuole può farsi avvisare proprio di questo, attivando l'avviso "minimo storico" sul carrello.

## Manutenzione del proprio spazio (parti da realizzare)

I prodotti che spariscono dal sito osservato non vengono cancellati: restano nel catalogo, grigiati, finché l'utente non decide di pulirli. Il Product Picker offrirà la rimozione dei prodotti delistati, la rimozione selettiva e lo svuotamento completo del catalogo.

Infine, i dati restano dell'utente: dal Profilo potrà **esportare tutto** — catalogo, storico prezzi, carrelli, notifiche — in formati aperti (JSON o CSV), in qualunque momento e senza chiedere nulla a nessuno.
