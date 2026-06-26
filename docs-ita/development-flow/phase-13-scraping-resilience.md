# Fase 13 — Resilienza dello scraping (user-agent & opzioni di richiesta gestite dal core)

> Stato: 💡 idea / da dettagliare · **post-1.0** (oltre il perimetro della [1.0](../1-business/product-overview.md)) · Prerequisiti: Fase 12 (1.0) · [Indice del flusso](README.md)
>
> **Questa è un'annotazione, non ancora una fase specificata.** Cattura un'idea emersa durante la Fase 4: gli MVP qui sotto sono abbozzati e vanno dettagliati (analisi → proposta → ok) prima di diventare lavoro reale.

## Obiettivo

Far sì che le connessioni verso i siti su cui si fa scraping non risultino tutte dallo **stesso** user-agent (e, più in generale, dalla stessa "impronta" di richiesta), ma siano **decise dal core** secondo una logica centrale — così uno scraper non hardcoda il proprio UA e il comportamento di rete è coerente e governabile in un punto solo.

Motivazione: ridurre la probabilità di blocco/penalizzazione lato sito e rendere il traffico più realistico, restando dentro il principio di **politeness** già adottato (CTX-R1) — l'obiettivo è robustezza, non evasione aggressiva (resta un hobby project per ≤5 utenti, [security posture](../2-architecture/security-posture.md)).

## Risultato apprezzabile

Due run successive (o due scraper) verso lo stesso sito partono con user-agent diversi secondo la strategia del core; lo scraper può, se serve, indicare una preferenza, ma non gestisce il dettaglio.

## Stato attuale (da cui si parte)

- `src/core/http.py` usa un **`DEFAULT_USER_AGENT` costante** (CTX-R2): unico, fisso, uguale per tutti.
- La config riservata per-scraper esiste già (`scraper_admin_config`, 4.B10: `politeness_delay_ms`/`http_timeout_s`/`cache_ttl_min`/`scrape_now_min_interval_s`) ed è il punto naturale dove agganciare eventuali chiavi nuove.
- `build_context` costruisce l'`HttpClient` per ogni run/scrape: è il seam dove il core può iniettare lo UA scelto.

## MVP (abbozzati — da dettagliare)

### Backend

- [ ] **13.B1 — User-agent deciso dal core** (~1h, *da dettagliare*): il core sceglie lo UA per ciascuna richiesta/run secondo una **strategia** (es. pool di UA realistici + rotazione/round-robin/random per run o per host), iniettato nell'`HttpClient` da `build_context`. Lo scraper **non** hardcoda lo UA. *Da decidere: rotazione per-richiesta vs per-run vs per-host; dove vive il pool (costante del core, config, file).*
- [ ] **13.B2 — Preferenza/override per-scraper** (~1h, *da dettagliare*): uno scraper può **influenzare** la scelta (es. forzare un UA specifico, o vincolare a un sottoinsieme del pool) — via chiave riservata in `scraper_admin_config` (estende 4.B10) e/o un hook del contratto `ScraperPlugin`. *Da decidere: solo raccomandazione (il core decide) vs override forte.*
- [ ] **13.B3 — Altre opzioni di richiesta coerenti** (~1h, *da valutare se serve*): header coerenti con lo UA scelto (es. `Accept-Language`), eventuale jitter del politeness, e altre opzioni di "impronta" gestite centralmente. *Da valutare: utilità reale a questa scala; proxy/rate per-host restano fuori scope salvo necessità.*

## Questioni aperte (design, da chiudere prima di iniziare)

- **Raccomandazione vs funzione del core**: il core *decide* lo UA (gli scraper lo subiscono) oppure offre una *funzione/strategia* che lo scraper invoca? La prima è più coerente con SCR-R6 ("il ritmo e il contatore sono imposti dal client, non lasciati al plugin").
- **Granularità della rotazione** (per richiesta / per run / per host) e **provenienza del pool** di user-agent.
- **Coerenza dell'impronta**: se si ruota lo UA, gli altri header dovrebbero essere coerenti (un UA "Chrome" con header incoerenti è controproducente).
- **Etica/ToS**: restare nel principio di politeness; questa è robustezza, non un sistema di evasione anti-bot.

## Riferimenti

[plugin-context](../4-capabilities/core/plugin-context.md) (CTX-R1..R4, `context.http`) · [scraper-plugin](../3-features/plugins/scraper-plugin.md) (SCR-R6) · config riservata per-scraper ([phase-04](phase-04-worker-scheduling.md) 4.B10) · [future-improvements/platform](../future-improvements/platform.md)
