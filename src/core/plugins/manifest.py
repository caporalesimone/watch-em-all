"""Plugin manifest parsing and validation (2.B1, REG-R1/R2).

The `manifest.json` is the plugin's declarative contract: everything the system
knows about it without executing it (manifest-reference.md). This module reads
and validates a single manifest. It enforces the rules that are knowable from
the file alone:

- JSON shape and required fields (pydantic);
- `name` is snake_case (it is the plugin_id and lands in SQL identifiers);
- `route_base` is kebab-case under `/plugins/` (when a frontend is present);
- the declared `type` matches the discovery folder it was found in;
- `api_version` matches the contract the core implements.

The remaining load-time rules — `name` uniqueness across plugins and the
imported class declaring the same `plugin_id` — need the whole set and the
running code, so they live in the registry (2.B2), not here.

Route convention (reconciles manifest-reference's `/plugins/<slug>` example with
the registry's `/api/plugins/...` mount): `route_base` is the canonical *frontend*
path, e.g. `/plugins/my-store`, used verbatim by the SPA. The backend mounts the
plugin router at `/api` + `route_base` (= `/api/plugins/my-store`).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

CORE_PLUGIN_API_VERSION = 1
"""The plugin-contract version the core implements. A manifest declaring a
different ``api_version`` is rejected (REG-R2)."""

PluginType = Literal["scraper", "notifier"]

# name: snake_case (lands in SQL identifiers, plugin_<name>_*).
_SNAKE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
# route_base: kebab-case slug under /plugins/ (lands in URLs).
_ROUTE_BASE_RE = re.compile(r"^/plugins/[a-z0-9]+(?:-[a-z0-9]+)*$")


class ManifestError(ValueError):
    """A manifest is missing, malformed, or violates a load-time rule (REG-R2)."""


class BackendSection(BaseModel):
    """`backend` block: the Python entry point and (notifiers) i18n folder."""

    model_config = ConfigDict(extra="forbid")

    entry: str = Field(min_length=1)  # relative to the plugin folder; exports `plugin`
    i18n: str | None = None


class FrontendSection(BaseModel):
    """`frontend` block. Omitted entirely by plugins without their own UI
    (notifiers): their config is rendered by the core, not shipped as a page."""

    model_config = ConfigDict(extra="forbid")

    entry: str = Field(min_length=1)  # relative; exports `default { component }`
    route_base: str
    i18n: str = Field(min_length=1)

    @field_validator("route_base")
    @classmethod
    def _kebab_under_plugins(cls, value: str) -> str:
        if not _ROUTE_BASE_RE.match(value):
            raise ValueError(
                "route_base must be a kebab-case slug under /plugins/ (e.g. /plugins/my-store)"
            )
        return value


class Manifest(BaseModel):
    """A validated plugin manifest."""

    model_config = ConfigDict(extra="forbid")

    name: str  # the plugin_id, snake_case (validated below)
    display_name: str = Field(min_length=1)
    type: PluginType
    version: str = Field(min_length=1)  # plugin's own version, informative
    api_version: int
    enabled: bool
    icon: str | None = None  # relative path inside the plugin folder
    backend: BackendSection
    frontend: FrontendSection | None = None

    @field_validator("name")
    @classmethod
    def _snake_case(cls, value: str) -> str:
        if not _SNAKE_RE.match(value):
            raise ValueError("name must be snake_case (it is the plugin_id and a table prefix)")
        return value


def parse_manifest(path: Path, *, folder_type: PluginType) -> Manifest:
    """Read and validate the manifest at ``path``, found in a ``folder_type`` folder.

    Raises :class:`ManifestError` with an explicit message on any violation; the
    caller (registry) turns that into a rejected plugin + a logged error, leaving
    the rest of the system running (REG-R5).
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ManifestError(f"cannot read manifest {path}: {exc}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ManifestError(f"manifest {path} is not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ManifestError(f"manifest {path} must be a JSON object")

    try:
        manifest = Manifest.model_validate(data)
    except ValidationError as exc:
        raise ManifestError(f"manifest {path} is invalid: {exc}") from exc

    if manifest.type != folder_type:
        raise ManifestError(
            f"manifest {path}: declared type {manifest.type!r} does not match its "
            f"folder (expected {folder_type!r})"
        )
    if manifest.api_version != CORE_PLUGIN_API_VERSION:
        raise ManifestError(
            f"manifest {path}: api_version {manifest.api_version} is incompatible with "
            f"the core (expects {CORE_PLUGIN_API_VERSION})"
        )
    return manifest
