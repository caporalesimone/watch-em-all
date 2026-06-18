"""Plugin Context — the object handed to every plugin in ``initialize()``.

The type is defined here (used by the registry's contract from 2.B2); the real
factory that builds it from the core engine/logger/config is wired in 2.B3
(:func:`build_context`).

Phase 2 scope (declared simplifications, flow rule #7):
- ``logger`` writes to stdout until the ``system_log`` table exists (~phase 10);
- ``config`` is empty until the ConfigField admin-config infrastructure exists
  (phases 7/9/10);
- no ``http``, ``update_catalog`` or ``markdown`` yet — they arrive with the
  scraper/notifier runtime in later phases.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from logging import Logger
from typing import Any

from sqlalchemy import Engine
from sqlalchemy.orm import Session


@dataclass
class PluginContext:
    """Everything a plugin may use, and by convention nothing else."""

    engine: Engine  # to create the plugin's OWN tables (own MetaData) in initialize()
    db: Session  # a session scoped to the plugin's own tables (plugin_<name>_*)
    logger: Logger  # namespaced; phase 2 -> stdout (system_log lands later)
    config: Mapping[str, Any]  # the plugin's admin-config section (empty in phase 2)
