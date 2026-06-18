"""Core plugin infrastructure (phase 2): manifest parsing, registry, context.

This package is the *core side* of the plugin system — the machinery that
discovers, validates and loads plugins. The plugins themselves live under
`src/plugins/{scrapers,notifiers}/<name>/` (build-system.md).
"""

from __future__ import annotations
