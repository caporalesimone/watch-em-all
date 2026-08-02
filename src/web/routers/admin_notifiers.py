"""Admin notifier API (endpoints.md, notifier-plugin.md). Phase 7 (7.B3/7.B4).

System-level notifier governance: list the loaded channels with their admin schema + state, set
the system config (secrets write-only), flip the global kill-switch (PCFG-R8) — including for the
in-app channel — and **validate** a channel. The in-app channel has no system config; only its
kill-switch applies.

**The flow this page enforces since 10.B28** (NOT-R9), and it is one loop rather than three
independent buttons: fill in the settings → *Validate*, which sends a real message and records
the settings as proven if the server takes it → only then can the channel be switched on. Editing
a validated setting switches the channel off again, because the proof was about the old value.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from src.core import notifiers as notif
from src.core.errors import APIError
from src.core.notify import send_test
from src.core.plugins.base import NotifierPlugin
from src.web.deps import AdminDep, SessionDep
from src.web.schemas import (
    AdminNotifierOut,
    NotifierConfigBody,
    NotifierEnabledBody,
    NotifierValidationOut,
)

router = APIRouter(prefix="/admin", tags=["Admin: notifiers"])


def _loaded(request: Request) -> dict[str, NotifierPlugin]:
    loaded = list(getattr(request.app.state, "loaded_plugins", []))
    return {
        lp.plugin.plugin_id: lp.plugin for lp in loaded if isinstance(lp.plugin, NotifierPlugin)
    }


def _sorted(plugins: dict[str, NotifierPlugin]) -> list[NotifierPlugin]:
    return sorted(plugins.values(), key=lambda p: (not notif.is_in_app(p.plugin_id), p.plugin_id))


def _get(request: Request, plugin_id: str) -> NotifierPlugin:
    plugin = _loaded(request).get(plugin_id)
    if plugin is None:
        raise APIError(404, "not_found", f"no notifier {plugin_id!r}")
    return plugin


def _admin_out(db: SessionDep, plugin: NotifierPlugin) -> AdminNotifierOut:
    pid = plugin.plugin_id
    schema = plugin.get_admin_config_schema()
    cfg = notif.admin_config(db, pid)
    complete = True if notif.is_in_app(pid) else notif.is_complete(schema, cfg)
    return AdminNotifierOut(
        plugin_id=pid,
        display_name=plugin.display_name or pid,
        is_in_app=notif.is_in_app(pid),
        admin_schema=schema,
        user_schema=plugin.get_user_config_schema(),
        config=notif.public_config(schema, cfg),
        is_set=notif.is_set_map(schema, cfg),
        enabled=notif.admin_enabled(db, pid),
        admin_config_complete=complete,
        requires_validation=notif.needs_validation(pid),
        validated=notif.is_validated(db, pid),
        validated_at=notif.validated_at(db, pid),
    )


@router.get(
    "/notifiers",
    response_model=list[AdminNotifierOut],
    summary="List the loaded notifier channels with their system config + kill-switch (admin).",
)
def list_admin_notifiers(
    request: Request, _admin: AdminDep, db: SessionDep
) -> list[AdminNotifierOut]:
    return [_admin_out(db, plugin) for plugin in _sorted(_loaded(request))]


@router.put(
    "/notifiers/{plugin_id}/config",
    response_model=AdminNotifierOut,
    summary="Set a channel's system config (keys filtered; secrets write-only).",
)
def set_admin_config(
    plugin_id: str, body: NotifierConfigBody, request: Request, _admin: AdminDep, db: SessionDep
) -> AdminNotifierOut:
    plugin = _get(request, plugin_id)
    if notif.is_in_app(plugin_id):
        raise APIError(422, "in_app_no_config", "the in-app channel has no system config")
    notif.set_admin_config(db, plugin, body.config)
    return _admin_out(db, plugin)


@router.patch(
    "/notifiers/{plugin_id}",
    response_model=AdminNotifierOut,
    summary="Global kill-switch for a channel (PCFG-R8): off = unavailable to everyone.",
)
def set_admin_enabled(
    plugin_id: str, body: NotifierEnabledBody, request: Request, _admin: AdminDep, db: SessionDep
) -> AdminNotifierOut:
    plugin = _get(request, plugin_id)  # applies to in-app too (the only way to disable it)
    # Switching **on** is what validation gates (10.B28, NOT-R9). Switching off never is: a
    # kill-switch that could refuse would be useless in the one moment it exists for.
    if body.enabled and not notif.is_validated(db, plugin_id):
        raise APIError(
            422,
            "not_validated",
            "validate the settings first: a channel is switched on only once a message "
            "has actually left through it",
        )
    notif.set_admin_enabled(db, plugin_id, body.enabled)
    return _admin_out(db, plugin)


@router.post(
    "/notifiers/{plugin_id}/validate",
    response_model=NotifierValidationOut,
    summary="Send a real message through the channel and, if the server takes it, record it as "
    "validated (admin only).",
)
def validate(
    plugin_id: str, request: Request, admin: AdminDep, db: SessionDep
) -> NotifierValidationOut:
    """The probe that used to be called *Send test*, now with a consequence (10.B28).

    **What it proves, and what it deliberately does not.** The message goes to the admin's own
    account address (10.B25) — the address the system will really use, which is a better test of
    the server config than one typed for the occasion. If the server accepts it, the settings are
    recorded as validated: that is the whole claim. Whether the mail is then delivered, filed as
    spam or bounced is between that server and the recipient, and an installation cannot know it
    without becoming a mail monitor.

    Failure records nothing, so a channel never drifts into "validated" by having been tried.
    """
    plugin = _get(request, plugin_id)
    if notif.is_in_app(plugin_id):
        # Nothing to prove and nowhere to send: in-app is validated by construction.
        return NotifierValidationOut(ok=True, channel=_admin_out(db, plugin))
    if not notif.is_complete(plugin.get_admin_config_schema(), notif.admin_config(db, plugin_id)):
        raise APIError(
            422,
            "config_incomplete",
            "fill in the required settings before validating them",
        )
    try:
        send_test(db, plugin, admin.sub)
    except Exception as exc:
        return NotifierValidationOut(ok=False, error=str(exc), channel=_admin_out(db, plugin))
    notif.mark_validated(db, plugin_id)
    return NotifierValidationOut(ok=True, channel=_admin_out(db, plugin))
