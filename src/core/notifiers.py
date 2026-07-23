"""Notifier config resolution and channel-state (notifier-plugin.md, profile-and-notifiers.md).
Phase 7.

Two-level config (NOT-R2): the **admin** row (``notifier_admin_config``) holds the channel
infrastructure + the global kill-switch (``enabled``); the **user** row (``notifier_user_config``)
holds the personal fields + the user's own on/off. Both are declared by the plugin as
``list[ConfigField]`` and the core persists them opaquely.

This module is the single place that:

- **filters keys on the declared schema** when saving (CFG-R5) — a user can never inject an admin
  key, and vice-versa; unknown keys are dropped and logged;
- keeps **secrets write-only** (CFG-R3): a save omitting a secret key leaves the stored value
  untouched; reads never return the value, only an ``is_set`` flag;
- **merges** admin+user config for delivery (the plugin's ``send`` receives the merge);
- resolves the **composite channel state** (available / active) a channel has for a user.

The **in-app** channel is special-cased (``IN_APP_PLUGIN_ID``): it has no config, the user cannot
disable it (always active for the user), and only the admin kill-switch can turn it off.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from src.core.models import NotifierAdminConfig, NotifierUserConfig

if TYPE_CHECKING:
    from src.core.contracts import ConfigField
    from src.core.plugins.base import NotifierPlugin

log = logging.getLogger(__name__)

IN_APP_PLUGIN_ID = "in_app"
"""The built-in in-app channel: always active for the user (no user toggle), governed only by
the admin kill-switch. Special-cased throughout — it has neither admin nor user config."""


def is_in_app(plugin_id: str) -> bool:
    return plugin_id == IN_APP_PLUGIN_ID


# --------------------------------------------------------------------------- schema helpers


def _schema_keys(schema: list[ConfigField]) -> set[str]:
    return {f.key for f in schema}


def _filter_keys(
    schema: list[ConfigField], incoming: dict[str, Any], *, side: str
) -> dict[str, Any]:
    """Keep only keys declared in ``schema`` (CFG-R5); drop and log the rest."""
    allowed = _schema_keys(schema)
    kept = {k: v for k, v in incoming.items() if k in allowed}
    dropped = set(incoming) - allowed
    if dropped:
        log.warning("notifier config: dropped non-%s key(s) %s", side, sorted(dropped))
    return kept


def _missing_required(schema: list[ConfigField], config: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for f in schema:
        if not f.required:
            continue
        v = config.get(f.key)
        if v is None or (isinstance(v, str) and not v.strip()):
            missing.append(f.key)
    return missing


def is_complete(schema: list[ConfigField], config: dict[str, Any]) -> bool:
    """All required fields present and non-empty (a saved secret counts as present)."""
    return not _missing_required(schema, config)


def is_set_map(schema: list[ConfigField], config: dict[str, Any]) -> dict[str, bool]:
    """Per secret field, whether a value is stored (CFG-R3) — never the value itself."""
    out: dict[str, bool] = {}
    for f in schema:
        if f.secret:
            v = config.get(f.key)
            out[f.key] = bool(v)
    return out


def public_config(schema: list[ConfigField], config: dict[str, Any]) -> dict[str, Any]:
    """The stored config with secret values stripped (CFG-R3) — safe to send to the client."""
    secret = {f.key for f in schema if f.secret}
    return {k: v for k, v in config.items() if k not in secret}


def _apply_save(
    schema: list[ConfigField], stored: dict[str, Any], incoming: dict[str, Any], *, side: str
) -> dict[str, Any]:
    """Merge ``incoming`` over ``stored``: keys are filtered on the schema; a secret key that is
    absent (or empty) in ``incoming`` keeps the stored value (CFG-R3, "absent = do not change")."""
    filtered = _filter_keys(schema, incoming, side=side)
    secret = {f.key for f in schema if f.secret}
    result = dict(stored)
    for k, v in filtered.items():
        if k in secret and (v is None or (isinstance(v, str) and not v.strip())):
            continue  # do not overwrite a stored secret with an empty submission
        result[k] = v
    return result


# --------------------------------------------------------------------------- admin config


def get_admin_row(db: Session, plugin_id: str) -> NotifierAdminConfig | None:
    return db.get(NotifierAdminConfig, plugin_id)


def admin_enabled(db: Session, plugin_id: str) -> bool:
    """The admin kill-switch (default True when no row exists)."""
    row = get_admin_row(db, plugin_id)
    return True if row is None else row.enabled


def admin_config(db: Session, plugin_id: str) -> dict[str, Any]:
    row = get_admin_row(db, plugin_id)
    return dict(row.config_json) if row is not None else {}


def set_admin_config(
    db: Session, plugin: NotifierPlugin, incoming: dict[str, Any]
) -> dict[str, Any]:
    """Upsert the admin config for a notifier, filtering keys on the admin schema and keeping
    secrets write-only. Returns the new stored config. Commits."""
    schema = plugin.get_admin_config_schema()
    row = get_admin_row(db, plugin.plugin_id)
    stored = dict(row.config_json) if row is not None else {}
    new_config = _apply_save(schema, stored, incoming, side="admin")
    if row is None:
        db.add(NotifierAdminConfig(plugin_id=plugin.plugin_id, config_json=new_config))
    else:
        row.config_json = new_config
    db.commit()
    return new_config


def set_admin_enabled(db: Session, plugin_id: str, enabled: bool) -> None:
    """Flip the admin kill-switch, preserving any stored config. Commits."""
    row = get_admin_row(db, plugin_id)
    if row is None:
        db.add(NotifierAdminConfig(plugin_id=plugin_id, config_json={}, enabled=enabled))
    else:
        row.enabled = enabled
    db.commit()


# --------------------------------------------------------------------------- user config


def get_user_row(db: Session, user_id: int, plugin_id: str) -> NotifierUserConfig | None:
    return db.get(NotifierUserConfig, (user_id, plugin_id))


def user_config(db: Session, user_id: int, plugin_id: str) -> dict[str, Any]:
    row = get_user_row(db, user_id, plugin_id)
    return dict(row.config_json) if row is not None else {}


def user_enabled(db: Session, user_id: int, plugin_id: str) -> bool:
    """The user's own on/off (in-app is always on; other channels default off)."""
    if is_in_app(plugin_id):
        return True
    row = get_user_row(db, user_id, plugin_id)
    return bool(row and row.enabled)


def set_user_config(
    db: Session, plugin: NotifierPlugin, user_id: int, incoming: dict[str, Any]
) -> dict[str, Any]:
    """Upsert a user's personal config for a notifier, filtering keys on the user schema and
    keeping secrets write-only. Returns the new stored config. Commits."""
    schema = plugin.get_user_config_schema()
    row = get_user_row(db, user_id, plugin.plugin_id)
    stored = dict(row.config_json) if row is not None else {}
    new_config = _apply_save(schema, stored, incoming, side="user")
    if row is None:
        db.add(
            NotifierUserConfig(user_id=user_id, plugin_id=plugin.plugin_id, config_json=new_config)
        )
    else:
        row.config_json = new_config
    db.commit()
    return new_config


def set_user_enabled(db: Session, user_id: int, plugin_id: str, enabled: bool) -> None:
    """Activate/deactivate a channel for a user, keeping the config (PROF-R10). Commits."""
    row = get_user_row(db, user_id, plugin_id)
    if row is None:
        db.add(
            NotifierUserConfig(
                user_id=user_id, plugin_id=plugin_id, config_json={}, enabled=enabled
            )
        )
    else:
        row.enabled = enabled
    db.commit()


# --------------------------------------------------------------------------- merge + state


def merged_config(db: Session, plugin: NotifierPlugin, user_id: int) -> dict[str, Any]:
    """The admin+user config a notifier's ``send`` receives: each side filtered on its own schema,
    the user's keys layered over the admin's."""
    admin = _filter_keys(
        plugin.get_admin_config_schema(), admin_config(db, plugin.plugin_id), side="admin"
    )
    user = _filter_keys(
        plugin.get_user_config_schema(), user_config(db, user_id, plugin.plugin_id), side="user"
    )
    return {**admin, **user}


@dataclass
class ChannelState:
    """The composite state of a channel for one user (profile-and-notifiers.md, PROF-R6/R7)."""

    plugin_id: str
    display_name: str
    is_in_app: bool
    admin_enabled: bool  # the admin kill-switch
    admin_config_complete: bool  # system config filled (always True for in-app)
    available: bool  # visible/usable by the user (admin_enabled AND admin_config_complete)
    user_config_complete: bool  # the user's required fields are filled (True for in-app)
    user_enabled: bool  # the user's own flag (always True for in-app)
    active: bool  # delivers: available AND user_config_complete AND user_enabled


def resolve_state(db: Session, plugin: NotifierPlugin, user_id: int) -> ChannelState:
    """Resolve the full state a channel has for ``user_id`` (the model in the state table of
    profile-and-notifiers.md). In-app: no config gate, always user-active; only the admin
    kill-switch can make it unavailable."""
    pid = plugin.plugin_id
    a_enabled = admin_enabled(db, pid)
    if is_in_app(pid):
        available = a_enabled
        return ChannelState(
            plugin_id=pid,
            display_name=plugin.display_name or pid,
            is_in_app=True,
            admin_enabled=a_enabled,
            admin_config_complete=True,
            available=available,
            user_config_complete=True,
            user_enabled=True,
            active=available,
        )
    a_complete = is_complete(plugin.get_admin_config_schema(), admin_config(db, pid))
    available = a_enabled and a_complete
    u_cfg = user_config(db, user_id, pid)
    u_complete = is_complete(plugin.get_user_config_schema(), u_cfg)
    u_enabled = user_enabled(db, user_id, pid)
    return ChannelState(
        plugin_id=pid,
        display_name=plugin.display_name or pid,
        is_in_app=False,
        admin_enabled=a_enabled,
        admin_config_complete=a_complete,
        available=available,
        user_config_complete=u_complete,
        user_enabled=u_enabled,
        active=available and u_complete and u_enabled,
    )
