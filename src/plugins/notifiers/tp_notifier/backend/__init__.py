"""TP Notifier — a throwaway Test Plugin (phase 2 only).

Proves the notifier branch of the registry: it loads, creates its own table, and
is listed by GET /api/plugins as type "notifier" — yet never appears in the
sidebar and registers no routes (a notifier has no own UI; its config lands in
later phases). It does NOT send anything. Delete this folder once a real notifier
exists.
"""

from __future__ import annotations

from sqlalchemy import Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from src.core.plugins.base import NotifierPlugin
from src.core.plugins.context import PluginContext


class _Base(DeclarativeBase):
    """The plugin's own metadata, separate from the core schema (CTX-R6)."""


class Outbox(_Base):
    __tablename__ = "plugin_tp_notifier_outbox"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    note: Mapped[str] = mapped_column(String(64), nullable=False, default="")


class TpNotifierPlugin(NotifierPlugin):
    plugin_id = "tp_notifier"

    def initialize(self, context: PluginContext) -> None:
        _Base.metadata.create_all(context.engine)
        context.logger.info("tp_notifier initialized; own table ensured")


plugin = TpNotifierPlugin()
