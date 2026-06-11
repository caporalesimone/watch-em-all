# Contratto — `ConfigField` (form dinamici)

> **Layer 4 — Contratto** · Audience: developer, plugin developer · Pseudocodice ammesso. Feature: [plugin-configuration](../../3-features/admin/plugin-configuration.md), [profile-and-notifiers](../../3-features/user/profile-and-notifiers.md).

## Scopo

Descrivere dichiarativamente un campo di configurazione, così che il core renderizzi i form di **admin** e **utente** di qualunque plugin senza conoscerne i campi. Un solo componente form nel design system, riusato ovunque.

## Modello

```python
from pydantic import BaseModel, model_validator
from typing import Literal

class ConfigField(BaseModel):
    key: str                       # chiave nella config persistita
    label_key: str                 # CHIAVE di traduzione (namespace del plugin), non testo fisso
    type: Literal["text", "email", "password", "url", "number", "bool", "select"]
    required: bool = False
    secret: bool = False           # mascherato in UI, write-only
    placeholder: str | None = None
    help_key: str | None = None    # chiave di traduzione per l'help
    options: list[str] | None = None       # solo per select
    default: str | int | bool | None = None   # coerente con type

    @model_validator(mode="after")
    def _password_is_secret(self):
        if self.type == "password":
            self.secret = True     # una password è sempre secret
        return self
```

## Regole

- **CFG-R1** — Ogni plugin espone `get_admin_config_schema()` e `get_user_config_schema()` come `list[ConfigField]`; il core genera i form dal solo schema.
- **CFG-R2** — Le etichette sono **chiavi di traduzione** risolte nel namespace locales del plugin (frontend): i form sono multilingua senza testo cablato nel backend.
- **CFG-R3** — Campi `secret`: mascherati, write-only — il server **non rispedisce mai** il valore; un valore già impostato è segnalato con un flag `is_set`, e l'assenza del campo nel salvataggio significa "non modificare".
- **CFG-R4** — Validazione UI da `type`/`required`/`options`; la validazione **autoritativa** è nel backend del plugin.
- **CFG-R5** — Al salvataggio della config **utente**, il backend **filtra le chiavi sullo schema utente** (chiavi estranee scartate e loggate): un utente non può iniettare chiavi admin. Stessa regola, simmetrica, per l'admin.
- **CFG-R6** — `default` tipizzato coerentemente col `type` (es. `587`, `True` — non stringhe).

## Esempio (notifier generico via canale di posta)

```python
# schema ADMIN (infrastruttura del canale)
[ConfigField(key="host", label_key="cfg.host", type="text", required=True),
 ConfigField(key="port", label_key="cfg.port", type="number", default=587),
 ConfigField(key="username", label_key="cfg.user", type="text"),
 ConfigField(key="password", label_key="cfg.pass", type="password"),   # secret implicito
 ConfigField(key="use_tls", label_key="cfg.tls", type="bool", default=True)]

# schema UTENTE (recapito personale)
[ConfigField(key="to_address", label_key="cfg.to", type="email", required=True)]
```

Il form generato include, per i notifier, il bottone **Test** (PROF-R8) e il flag di attivazione per-utente (gestito dal core, non dichiarato nello schema).
