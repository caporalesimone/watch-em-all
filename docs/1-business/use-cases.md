# Casi d'uso principali

> **Layer 1 — Business** · Audience: tutti · Solo testo descrittivo.

I due casi d'uso fondanti del prodotto. Ogni scelta di design deve poter essere ricondotta a uno di questi.

## UC-1 — L'acquisto in blocco al massimo risparmio

> *"Tengo d'occhio un certo numero di prodotti e li compro in blocco nel momento in cui il risparmio complessivo mi appaga."*

Marco colleziona giochi da tavolo. Sul suo negozio online preferito ha individuato dodici titoli che vuole comprare, ma non ha fretta: sa che i prezzi oscillano e che, comprando tutto insieme, supererebbe la soglia di spesa oltre la quale il negozio applica uno sconto aggiuntivo e la spedizione gratuita.

Con Watch 'Em All, Marco:

1. configura lo scraper del negozio indicando i prodotti (o le categorie) da osservare;
2. crea un carrello "Wishlist giochi" e ci mette i dodici titoli;
3. imposta la soglia: *"avvisami quando il totale scende sotto i 300 €"* (oppure: *"quando il risparmio supera il 25%"*);
4. sceglie quando ricevere gli avvisi (ad esempio ogni sera alle 22).

Da quel momento il sistema osserva per lui. La sera in cui il totale del carrello — inclusi gli sconti a soglia e le spese di spedizione che il negozio applicherebbe — scende sotto la soglia, Marco riceve **una notifica**: è il momento di comprare tutto in blocco. Nel frattempo, lo storico prezzi gli mostra se sta guardando un minimo reale o un'oscillazione qualunque.

**Cosa richiede questo caso d'uso al sistema**: carrelli con totali calcolati come li calcolerebbe il negozio (sconti a soglia, spedizione — i cosiddetti *adjustments*), soglie assolute o percentuali, notifica aggregata, storico dei prezzi.

## UC-2 — Lo stesso prodotto su più siti

> *"Monitoro un certo prodotto su più siti differenti e voglio sapere quando va in offerta su uno qualunque di questi."*

Giulia vuole una specifica macchina fotografica, venduta da tre negozi online diversi. Non le interessa da chi comprarla: le interessa il primo che la sconta.

Con Watch 'Em All, Giulia:

1. configura i tre scraper (uno per negozio) sullo stesso prodotto;
2. crea un **carrello cross-scraper** "Fotocamera" e inserisce il prodotto **tre volte: una per ogni sito**;
3. attiva gli avvisi di tipo "prodotto in offerta" e "prodotto di nuovo disponibile".

Quando uno dei tre negozi sconta la fotocamera, Giulia riceve la notifica, e dentro il carrello vede **chiaramente da quale sito proviene ogni riga**: la provenienza (nome e icona del negozio) è sempre visibile accanto a ogni prodotto, sia nella pagina dei carrelli sia nella notifica. Senza questa informazione il carrello cross sarebbe illeggibile — tre righe identiche senza sapere chi sconta.

**Cosa richiede questo caso d'uso al sistema**: carrelli che accettano prodotti da scraper diversi, lo "stesso" prodotto presente più volte (una per sito), **provenienza sempre esplicita** su ogni riga, avvisi a livello di singolo prodotto dentro il carrello.

## Casi d'uso di contorno

- **Sorveglianza della disponibilità**: prodotti che vanno e vengono dallo stock; l'avviso "di nuovo disponibile" vale quanto quello di sconto.
- **Report periodico**: anche senza eventi, l'utente può chiedere un riepilogo settimanale o mensile dello stato dei suoi carrelli, per mantenere il polso della situazione.
- **Amministrazione**: l'admin decide quante volte al giorno girano gli scraper, controlla quanto lavoro fanno e interviene se qualcosa si rompe. Vedi [admin-experience.md](admin-experience.md).
