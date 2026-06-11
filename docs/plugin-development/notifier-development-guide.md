# Guida — Sviluppare un notifier

> Audience: plugin developer. Contratto normativo: [3-features/plugins/notifier-plugin.md](../3-features/plugins/notifier-plugin.md) · Payload: [alert-event](../4-capabilities/contracts/alert-event.md).

## Il contratto da implementare

```python
from core.plugins import NotifierPlugin, PluginContext
from core.contracts import AlertEvent, SummaryReport, TextMessageEvent, ConfigField

class MioNotifier(NotifierPlugin):
    plugin_id    = "mio_canale"           # == manifest.name
    display_name = "Mio Canale"

    def initialize(self, context: PluginContext) -> None:
        ...   # di solito niente tabelle: la config la persiste il core

    def send(self, notification: AlertEvent | SummaryReport | TextMessageEvent,
             config: dict, locale: str) -> None:
        # config = merge admin+utente GIÀ fatto (e filtrato) dal core
        # 1. formatta in base a notification.kind (digest = diff, summary = snapshot,
        #    *_message = titolo + body Markdown: rendi con context.markdown, MAI parsing tuo)
        # 2. traduci con i TUOI file lingua backend (backend/locales/{locale}.json)
        # 3. invia sul canale via context.http (o protocollo dedicato, es. SMTP)
        # 4. errori transitori: riprova 2-3 volte con backoff; poi solleva
        #    NotifierDeliveryError("motivo leggibile") — il core registra l'esito
        ...

    def send_test(self, config: dict, locale: str) -> None:
        # notifica di prova con la config corrente; usata dal bottone Test (utente e admin)
        ...

    def get_admin_config_schema(self) -> list[ConfigField]: ...
    def get_user_config_schema(self)  -> list[ConfigField]: ...
```

## Cosa fa il core per te (non rifarlo)

- Decide quando inviare e costruisce il contenuto.
- Scrive **sempre** lo storico interno (prima della consegna): se il tuo canale fallisce, l'utente non perde nulla.
- Itera i canali attivi dell'utente, fa il merge config (chiavi utente filtrate sullo schema utente), registra l'esito per canale.
- Ti passa la **lingua** dell'utente.

## Formattazione: i requisiti sul contenuto

Qualunque sia il formato del canale, devono sopravvivere (NOT-R7):

| Dal payload | Perché |
|---|---|
| Tag degli eventi per prodotto | è la notizia |
| Prezzo prima → dopo, % sconto | decidere senza aprire l'app |
| **Provenienza** di ogni prodotto | indispensabile nei carrelli cross |
| Link al prodotto | andare a comprare |
| Totali del carrello + stato soglia | il quadro d'insieme (UC-1) |

Tre payload, distinti da `kind`:

- `alert_digest` — un diff: racconta **cosa è cambiato**.
- `summary` — uno snapshot: racconta **come stanno le cose**.
- `system_message` / `admin_message` — un **messaggio testuale** (titolo + body). Il body è **Markdown**: rendilo con gli helper del contesto — `context.markdown.to_html(body)` per i canali HTML, `context.markdown.strip(body)` per quelli a testo puro, pass-through se il canale parla markdown nativamente. Regola d'oro (NOT-R8): **degrada, non fallire mai** per il formato. Qui non c'è nulla da tradurre: il testo è dell'autore del messaggio.

## Config a due livelli (esempio canale di messaggistica via webhook)

```python
def get_admin_config_schema(self):
    return []   # nessuna infrastruttura di sistema: canale interamente personale

def get_user_config_schema(self):
    return [ConfigField(key="webhook_url", label_key="cfg.webhook", type="url", required=True)]
```

Un canale come la posta elettronica avrà invece uno schema admin corposo (host, porta, credenziali — `type="password"` è automaticamente secret) e uno schema utente minimo (l'indirizzo). Se il tuo canale richiede config admin, finché l'admin non la compila il core mostra il canale come "non disponibile": non devi gestirlo tu.

## Errori: il pattern richiesto

```python
def send(self, n, config, locale):
    payload = self._format(n, locale)
    for attempt in range(3):
        try:
            self._deliver(payload, config); return
        except TransientError:
            sleep(2 ** attempt)
    raise NotifierDeliveryError(f"{self.display_name}: canale non raggiungibile")
```

Pochi tentativi, backoff, poi un errore **descrittivo**: finisce nello storico dell'utente ("consegna fallita: …") e nel log admin. Mai inghiottire l'errore, mai retry infiniti.

## Traduzioni backend

`backend/locales/it.json`, `en.json`: i testi delle notifiche (oggetti, intestazioni, etichette dei tag). `locale` arriva alla `send`; fallback sulla lingua di default se il file manca. Le traduzioni della tua eventuale UI stanno invece in `frontend/locales/`.

## Prima del rilascio

[Checklist](checklist-and-testing.md): tutti i `kind` formattati (markdown via helper per i messaggi testuali), provenienza presente, send_test funzionante, errori descrittivi, traduzioni complete nelle lingue del core.
