"""Admin notifier API (endpoints.md, notifier-plugin.md). Phase 7 (7.B3/7.B4).

System-level notifier governance: list the loaded channels with their admin schema + state, set
the system config (secrets write-only), flip the global kill-switch (PCFG-R8) — including for the
in-app channel — and probe a channel with an admin-supplied target. The in-app channel has no
system config; only its kill-switch applies.
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
    NotifierTestResult,
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
    notif.set_admin_enabled(db, plugin_id, body.enabled)
    return _admin_out(db, plugin)


@router.post(
    "/notifiers/{plugin_id}/test",
    response_model=NotifierTestResult,
    summary="Probe a channel with the system config, delivered to the admin's own account.",
)
def admin_test(
    plugin_id: str, request: Request, admin: AdminDep, db: SessionDep
) -> NotifierTestResult:
    """The target used to be typed into the form; since 10.B25 it is the admin's own account
    address. Nothing is lost — this probe answers *"does the server config work"*, and an
    address the admin types is a worse test of that than the one the system will really use."""
    plugin = _get(request, plugin_id)
    if notif.is_in_app(plugin_id):
        return NotifierTestResult(ok=True)  # nothing to test
    try:
        send_test(db, plugin, admin.sub)
        return NotifierTestResult(ok=True)
    except Exception as exc:
        return NotifierTestResult(ok=False, error=str(exc))
