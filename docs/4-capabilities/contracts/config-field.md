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
- **CFG-R7** (10.F26) — `width` (`full` | `half` | `third` | `quarter`, default `full`) says **how
  much of a row** a field asks for. The core renders a 12-column grid and honours it from the `sm`
  breakpoint up; below that every field is full width. It belongs to the schema because only the
  plugin knows which of its fields are **one thought** — a host, its port and its TLS switch are an
  SMTP server, and read down a column of six the admin has to assemble that themselves. The core
  cannot infer it, since it never learns a field name (CFG-R1), and putting it in the frontend
  would be one rule about one field written twice, in two languages. It is a hint about
  relatedness, not a layout: the renderer decides when there is room to honour it.

## Example (email notifier)

```python
# ADMIN schema (channel infrastructure)
[ConfigField(key="smtp_host", label_key="email.cfg.host", type="text", required=True),
 ConfigField(key="smtp_port", label_key="email.cfg.port", type="number", default=587),
 ConfigField(key="smtp_user", label_key="email.cfg.user", type="text"),
 ConfigField(key="smtp_password", label_key="email.cfg.pass", type="password"),  # secret
 ConfigField(key="use_tls", label_key="email.cfg.tls", type="bool", default=True),
 ConfigField(key="from_address", label_key="email.cfg.from", type="email", required=True)]

# USER schema — empty for email since 10.B25: the recipient is the account, not a
# field. A channel with a genuinely personal setting still declares one here.
[]
```

Notifier forms also carry a **Test** button and the per-user activation flag (managed by the core,
not declared in the schema).
