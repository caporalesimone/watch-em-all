"""In-app notifier — the built-in delivery channel (phase 7).

The in-app history (``alert_log``) is written by the core for every digest, so this channel's
"delivery" is the record itself: :func:`src.core.notify.enqueue_deliveries` marks the in-app
``alert_delivery`` row ``delivered`` inline (no network, never drained), so ``send`` is a no-op.
It exists as a real notifier so the channel is uniform with email/Teams — it appears in the
channel list and is governed by the admin kill-switch — with two differences the core enforces:
the **user cannot disable it** (always active for the user) and it has **no config**. Only the
admin can turn it off globally, in which case the inbox stops surfacing digests for everyone.
"""

from __future__ import annotations

from typing import Any

from src.core.alert_engine import AlertEvent
from src.core.plugins.base import NotifierPlugin


class InAppNotifierPlugin(NotifierPlugin):
    plugin_id = "in_app"
    display_name = "In-app"
    # No tables (table_metadata stays None) and no config schema: the core owns the record.

    def send(self, notification: AlertEvent, config: dict[str, Any], locale: str) -> None:
        return  # no-op: the alert_log row IS the in-app delivery (marked inline by the core)

    def send_test(self, config: dict[str, Any], locale: str) -> None:
        return  # nothing to test: the in-app channel is always available to the user


plugin = InAppNotifierPlugin()
