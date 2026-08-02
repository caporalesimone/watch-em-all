"""User notifier API (endpoints.md, profile-and-notifiers.md). Phase 7 (7.B3/7.B4).

The channels section of the Profile: list the notifiers available to the user with their personal
schema + composite state, save personal config (secrets write-only) and toggle a channel on/off.
Channels the admin has globally disabled are not listed. The in-app channel is shown but has no
user config and cannot be disabled (always active for the user).

**No test send here since 10.X4.** It made sense while a user typed their own delivery address
into this page; since 10.B23/10.B25 the address *is* the account, and it has already proved it
works by carrying the password that person signed in with. What was left was a button probing
the server's SMTP config from a page whose owner can do nothing about it — the admin's probe
(``POST /api/admin/notifiers/{id}/test``) is the same check where it can be acted on.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from src.core import notifiers as notif
from src.core.errors import APIError
from src.core.plugins.base import NotifierPlugin
from src.web.deps import SessionDep, UserDep
from src.web.schemas import NotifierChannelOut, NotifierConfigBody, NotifierEnabledBody

router = APIRouter(prefix="/notifiers", tags=["Notifiers"])


def _loaded(request: Request) -> dict[str, NotifierPlugin]:
    loaded = list(getattr(request.app.state, "loaded_plugins", []))
    return {
        lp.plugin.plugin_id: lp.plugin for lp in loaded if isinstance(lp.plugin, NotifierPlugin)
    }


def _sorted(plugins: dict[str, NotifierPlugin]) -> list[NotifierPlugin]:
    # In-app first, then the rest alphabetically.
    return sorted(plugins.values(), key=lambda p: (not notif.is_in_app(p.plugin_id), p.plugin_id))


def _get(request: Request, plugin_id: str) -> NotifierPlugin:
    plugin = _loaded(request).get(plugin_id)
    if plugin is None:
        raise APIError(404, "not_found", f"no notifier {plugin_id!r}")
    return plugin


def _channel_out(db: SessionDep, plugin: NotifierPlugin, user_id: int) -> NotifierChannelOut:
    state = notif.resolve_state(db, plugin, user_id)
    schema = plugin.get_user_config_schema()
    cfg = notif.user_config(db, user_id, plugin.plugin_id)
    return NotifierChannelOut(
        plugin_id=plugin.plugin_id,
        display_name=plugin.display_name or plugin.plugin_id,
        is_in_app=state.is_in_app,
        user_schema=schema,
        config=notif.public_config(schema, cfg),
        is_set=notif.is_set_map(schema, cfg),
        available=state.available,
        user_config_complete=state.user_config_complete,
        enabled=state.user_enabled,
        active=state.active,
    )


@router.get(
    "",
    response_model=list[NotifierChannelOut],
    summary="List the notifier channels available to the user with their composite state.",
)
def list_notifiers(request: Request, user: UserDep, db: SessionDep) -> list[NotifierChannelOut]:
    out: list[NotifierChannelOut] = []
    for plugin in _sorted(_loaded(request)):
        if not notif.admin_enabled(db, plugin.plugin_id):
            continue  # admin kill-switch off → invisible to users
        out.append(_channel_out(db, plugin, user.sub))
    return out


@router.put(
    "/{plugin_id}/config",
    response_model=NotifierChannelOut,
    summary="Save the user's personal config for a channel (keys filtered; secrets write-only).",
)
def set_config(
    plugin_id: str, body: NotifierConfigBody, request: Request, user: UserDep, db: SessionDep
) -> NotifierChannelOut:
    plugin = _get(request, plugin_id)
    if notif.is_in_app(plugin_id):
        raise APIError(422, "in_app_no_config", "the in-app channel has no user config")
    notif.set_user_config(db, plugin, user.sub, body.config)
    return _channel_out(db, plugin, user.sub)


@router.patch(
    "/{plugin_id}",
    response_model=NotifierChannelOut,
    summary="Activate/deactivate a channel for the user (config preserved).",
)
def set_enabled(
    plugin_id: str, body: NotifierEnabledBody, request: Request, user: UserDep, db: SessionDep
) -> NotifierChannelOut:
    plugin = _get(request, plugin_id)
    if notif.is_in_app(plugin_id):
        raise APIError(422, "in_app_always_active", "the in-app channel cannot be disabled")
    notif.set_user_enabled(db, user.sub, plugin_id, body.enabled)
    return _channel_out(db, plugin, user.sub)
