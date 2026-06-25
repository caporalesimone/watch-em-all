"""Plugin discovery API (2.B4, REG-R6).

``GET /api/plugins`` lists the enabled + loaded plugins for the SPA — name, type,
route_base, icon URL, display_name — with no internal filesystem paths. Plugin
icons are served from ``/api/plugin-assets/{name}/icon`` (decision: backend
static mount). The plugins' own routers are mounted by the registry under
``/api{route_base}``, with a ``Plugin: <name>`` Swagger tag.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.core.errors import APIError
from src.core.plugins.manifest import PluginType
from src.core.plugins.registry import LoadedPlugin
from src.web.deps import UserDep

router = APIRouter()

# Explicit MIME for the icon types we serve (Python's mimetypes is shaky on .ico).
_ICON_MEDIA = {".ico": "image/x-icon", ".svg": "image/svg+xml"}


class PluginInfo(BaseModel):
    """What the SPA needs to mount a plugin — nothing internal (REG-R6)."""

    name: str
    type: PluginType
    route_base: str | None
    icon: str | None
    display_name: str


def _loaded(request: Request) -> list[LoadedPlugin]:
    return list(getattr(request.app.state, "loaded_plugins", []))


@router.get(
    "/plugins",
    response_model=list[PluginInfo],
    tags=["Plugins"],
    summary="List the enabled, loaded plugins for the SPA (name, type, route, icon).",
)
def list_plugins(request: Request, _user: UserDep) -> list[PluginInfo]:
    infos: list[PluginInfo] = []
    for loaded in _loaded(request):
        manifest = loaded.manifest
        route_base = manifest.frontend.route_base if manifest.frontend else None
        icon = f"/api/plugin-assets/{manifest.name}/icon" if loaded.icon_path else None
        infos.append(
            PluginInfo(
                name=manifest.name,
                type=manifest.type,
                route_base=route_base,
                icon=icon,
                display_name=manifest.display_name,
            )
        )
    return infos


@router.get(
    "/plugin-assets/{plugin_name}/icon",
    tags=["Plugins"],
    summary="Serve a plugin's icon asset (public static asset, loaded as an <img>).",
)
def plugin_icon(plugin_name: str, request: Request) -> FileResponse:
    for loaded in _loaded(request):
        if loaded.manifest.name != plugin_name or loaded.icon_path is None:
            continue
        base = loaded.directory.resolve()
        icon_path = loaded.icon_path.resolve()
        # The icon must resolve to a real file strictly inside the plugin folder.
        if icon_path.is_file() and base in icon_path.parents:
            return FileResponse(icon_path, media_type=_ICON_MEDIA.get(icon_path.suffix.lower()))
        break
    raise APIError(404, "not_found", "plugin icon not found")
