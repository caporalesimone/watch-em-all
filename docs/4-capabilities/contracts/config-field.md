# Contract — `ConfigField` (dynamic forms)

> **Layer 4 — Contract** · Audience: developers, plugin developers · English mirror of the Italian
> reference [`docs-ita/4-capabilities/contracts/config-field.md`](../../../docs-ita/4-capabilities/contracts/config-field.md),
> limited to what is implemented (DOC-12, phase 7).

## Purpose

Describe a config field declaratively, so the core renders the **admin** and **user** forms of any
plugin without knowing its fields. One form component in the design system, reused everywhere.

## Model

```python
class ConfigField(BaseModel):
    key: str                        # key in the persisted config
    label_key: str                  # i18n KEY (not fixed text)
    type: Literal["text","email","password","url","number","bool","select"]
    required: bool = False
    secret: bool = False            # masked in the UI, write-only
    placeholder: str | None = None
    help_key: str | None = None
    options: list[str] | None = None       # select only
    default: str | int | bool | None = None # typed coherently with `type`
    # a password is always secret (enforced)
```

## Rules

- **CFG-R1** — Each plugin exposes `get_admin_config_schema()` and `get_user_config_schema()` as
  `list[ConfigField]`; the core builds the forms from the schema alone.
- **CFG-R2** — Labels are **i18n keys**. (For backend-only notifiers with no frontend namespace, the
  form falls back to a humanized key; V1 is English.)
- **CFG-R3** — `secret` fields are masked and **write-only**: the server never returns the value; a
  stored value is signalled by an `is_set` flag, and a save that omits the key means "do not change".
- **CFG-R4** — UI validation from `type`/`required`/`options`; the authoritative validation is the
  plugin's backend.
- **CFG-R5** — On save, the backend **filters keys on the relevant schema** (foreign keys dropped and
  logged): a user cannot inject an admin key, and vice-versa.
- **CFG-R6** — `default` typed coherently with `type` (e.g. `587`, `True`, not strings).

## Example (email notifier)

```python
# ADMIN schema (channel infrastructure)
[ConfigField(key="smtp_host", label_key="email.cfg.host", type="text", required=True),
 ConfigField(key="smtp_port", label_key="email.cfg.port", type="number", default=587),
 ConfigField(key="smtp_user", label_key="email.cfg.user", type="text"),
 ConfigField(key="smtp_password", label_key="email.cfg.pass", type="password"),  # secret
 ConfigField(key="use_tls", label_key="email.cfg.tls", type="bool", default=True),
 ConfigField(key="from_address", label_key="email.cfg.from", type="email", required=True)]

# USER schema (personal target)
[ConfigField(key="to_address", label_key="email.cfg.to", type="email", required=True)]
```

Notifier forms also carry a **Test** button and the per-user activation flag (managed by the core,
not declared in the schema).
