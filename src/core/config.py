"""Configuration loader (1.B1).

Bootstrap config lives in `config.yaml` (database URL, secret key, token TTLs,
default locale); secrets and a few non-secret container vars live in the
environment. config.yaml values may reference the environment with `${VAR}` or
`${VAR:-default}`; the loader resolves them at startup and validates the result,
failing fast with a clear message on a missing required value. The product
version is read from the file baked at build by `git describe` (1.T4).
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError

CONFIG_PATH = os.environ.get("WEA_CONFIG_FILE", "/app/config.yaml")
VERSION_PATH = os.environ.get("WEA_VERSION_FILE", "/app/VERSION")

# ${NAME} (required) or ${NAME:-default} (fallback when NAME is unset).
_INTERP = re.compile(r"\$\{(?P<name>[A-Za-z_][A-Za-z0-9_]*)(?::-(?P<default>[^}]*))?\}")


class ConfigError(RuntimeError):
    """Raised when the bootstrap configuration is missing or invalid."""


class CoreConfig(BaseModel):
    database_url: str = Field(min_length=1)
    secret_key: str = Field(min_length=16)  # AUTH-R3 (real keys are 64 hex chars)
    default_locale: str = "en"
    access_token_ttl_min: int = Field(gt=0)
    refresh_token_ttl_days: int = Field(gt=0)


class Settings(BaseModel):
    core: CoreConfig
    version: str
    admin_username: str
    admin_initial_password: str | None
    # 4.B0: gates only whether GET /api/health exposes schema drift (the check
    # always runs and logs). Unset → off; .env/.env.example ship it true.
    schema_drift_alert: bool = False


def _interpolate(value: str) -> str:
    def repl(match: re.Match[str]) -> str:
        name = match.group("name")
        env_value = os.environ.get(name)
        if env_value is not None:
            return env_value
        default = match.group("default")
        if default is not None:
            return default
        raise ConfigError(f"environment variable {name!r} referenced in config.yaml is not set")

    return _INTERP.sub(repl, value)


def _resolve(node: Any) -> Any:
    if isinstance(node, str):
        return _interpolate(node)
    if isinstance(node, dict):
        return {key: _resolve(val) for key, val in node.items()}
    if isinstance(node, list):
        return [_resolve(item) for item in node]
    return node


def _env_flag(name: str, *, default: bool = False) -> bool:
    """Read a boolean env flag: unset → ``default``; otherwise true for
    ``1`` / ``true`` / ``yes`` / ``on`` (case-insensitive)."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def read_version() -> str:
    """The running build's version, from the file baked at build by ``git describe`` (1.T4).

    Public and deliberately standalone — no config parsing, no cache — so callers that only
    need the version (the scraper User-Agent) can have it without a valid ``config.yaml``.
    """
    try:
        text = Path(VERSION_PATH).read_text(encoding="utf-8").strip()
    except OSError:
        return "0.0.0-unknown"
    return text or "0.0.0-unknown"


def load_settings(config_path: str | os.PathLike[str] | None = None) -> Settings:
    """Read, interpolate and validate the bootstrap configuration."""
    path = config_path if config_path is not None else CONFIG_PATH
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot read config file {path}: {exc}") from exc

    parsed = yaml.safe_load(raw) or {}
    if not isinstance(parsed, dict):
        raise ConfigError("config.yaml must be a mapping at the top level")
    resolved = _resolve(parsed)

    try:
        core = CoreConfig.model_validate(resolved.get("core", {}))
    except ValidationError as exc:
        raise ConfigError(f"invalid core configuration: {exc}") from exc

    return Settings(
        core=core,
        version=read_version(),
        admin_username=os.environ.get("WEA_ADMIN_INITIAL_USERNAME", "admin"),
        admin_initial_password=os.environ.get("WEA_ADMIN_INITIAL_PASSWORD") or None,
        schema_drift_alert=_env_flag("WEA_SCHEMA_DRIFT_ALERT"),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings, loaded once."""
    return load_settings()
