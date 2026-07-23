"""Channel dispatch + delivery drain (notification-architecture.md, alert-engine.md). Phase 7.

Delivery is decoupled from the alert run (the reasoning of 2026-07-22/23). The alert engine
always writes the digest to ``alert_log`` (the source of truth). This module then:

- :func:`enqueue_deliveries` — right after the digest is written, records one ``alert_delivery``
  row per **active** channel. The **in-app** channel is local, so it is marked ``delivered`` (or
  ``skipped`` if the admin disabled it) inline; network channels start ``pending``. When nothing
  will be delivered anywhere, a single ``skipped_no_notifier`` row is written.
- :func:`drain_deliveries` — a separate, periodic worker step that sends the ``pending`` network
  deliveries (the plugin does its own short retry/backoff) and records ``delivered`` / ``failed``.
  Best-effort: a ``failed`` row is never re-drained — the next digest carries the new state.

The engine never imports the notifier plugins; the caller (worker / web) passes the loaded
``NotifierPlugin`` instances in.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.alert_engine import AlertEvent
from src.core.models import AlertDelivery, AlertLog, User
from src.core.notifiers import (
    IN_APP_PLUGIN_ID,
    admin_enabled,
    is_in_app,
    merged_config,
    resolve_state,
)

if TYPE_CHECKING:
    from src.core.plugins.base import NotifierPlugin

log = logging.getLogger("wea.notifier")

_DELIVERABLE = ("delivered", "pending")


def enqueue_deliveries(db: Session, alert_log: AlertLog, notifiers: list[NotifierPlugin]) -> None:
    """Create the ``alert_delivery`` rows for a just-written digest (7.B2). In-app is delivered
    inline (or skipped if admin-disabled); active network channels start ``pending``; if nothing
    is deliverable, one ``skipped_no_notifier`` row is written. Commits."""
    user_id = alert_log.user_id
    rows: list[AlertDelivery] = []
    for n in notifiers:
        state = resolve_state(db, n, user_id)
        if is_in_app(n.plugin_id):
            status = "delivered" if state.available else "skipped"
            rows.append(_row(alert_log.id, n.plugin_id, status))
        elif state.active:
            rows.append(_row(alert_log.id, n.plugin_id, "pending"))

    if any(r.status in _DELIVERABLE for r in rows):
        for r in rows:
            db.add(r)
    else:
        db.add(_row(alert_log.id, "", "skipped_no_notifier"))
    db.commit()


def _row(alert_log_id: int, plugin_id: str, status: str) -> AlertDelivery:
    return AlertDelivery(alert_log_id=alert_log_id, plugin_id=plugin_id, status=status)


def drain_deliveries(db: Session, notifiers: list[NotifierPlugin]) -> int:
    """Send every ``pending`` delivery on its channel and record the outcome (7.B7 / the drain
    step). The plugin's ``send`` does its own retry/backoff; a failure is recorded as ``failed``
    with the reason and never re-tried here (best-effort). Returns the number processed."""
    by_id = {n.plugin_id: n for n in notifiers}
    pending = list(db.scalars(select(AlertDelivery).where(AlertDelivery.status == "pending")))
    for d in pending:
        plugin = by_id.get(d.plugin_id)
        log_row = db.get(AlertLog, d.alert_log_id)
        if plugin is None or log_row is None:
            d.status = "failed"
            d.error = "notifier not loaded" if plugin is None else "alert record missing"
            db.commit()
            continue
        user = db.get(User, log_row.user_id)
        locale = user.locale if user is not None else "en"
        try:
            event = AlertEvent.model_validate(log_row.payload_json)
            cfg = merged_config(db, plugin, log_row.user_id)
            plugin.send(event, cfg, locale)
            d.status = "delivered"
            d.error = None
        except Exception as exc:  # includes NotifierDeliveryError after the plugin's retries
            d.status = "failed"
            d.error = str(exc)[:500]
            log.warning("delivery failed: channel %s for user %s", d.plugin_id, log_row.user_id)
        db.commit()
    return len(pending)


def send_test(db: Session, plugin: NotifierPlugin, user_id: int) -> None:
    """Send a test notification with the user's current merged config (NOT-R6). Synchronous, no
    persistence — used by the user (own target) and, with an admin-supplied target, by the admin.
    Propagates the plugin's error (the caller turns it into a readable API error)."""
    user = db.get(User, user_id)
    locale = user.locale if user is not None else "en"
    plugin.send_test(merged_config(db, plugin, user_id), locale)


def send_test_with_config(
    db: Session, plugin: NotifierPlugin, user_id: int, extra_user_config: dict[str, object]
) -> None:
    """Admin channel check (POST /api/admin/notifiers/{id}/test): the admin config merged with an
    ad-hoc user target supplied in the request (not persisted). ``extra_user_config`` is filtered
    on the user schema by the caller."""
    user = db.get(User, user_id)
    locale = user.locale if user is not None else "en"
    cfg = {**merged_config(db, plugin, user_id), **extra_user_config}
    plugin.send_test(cfg, locale)


def in_app_visible(db: Session) -> bool:
    """Whether the in-app inbox should surface digests right now: true unless the admin has
    disabled the in-app channel (the alerts list/badge are gated on this). Defaults to true when
    no admin row exists — fail-open, never hide the source of truth."""
    return admin_enabled(db, IN_APP_PLUGIN_ID)
