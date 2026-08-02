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

- :func:`drain_message_deliveries` — the same drain for admin messages (10.B12), whose outcomes
  live in their own table because a broadcast has no ``alert_log`` row to hang them off.

The engine never imports the notifier plugins; the caller (worker / web) passes the loaded
``NotifierPlugin`` instances in.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.alert_engine import AlertEvent, TextMessageEvent
from src.core.contracts import NotificationKind
from src.core.models import AdminMessage, AdminMessageDelivery, AlertDelivery, AlertLog, User
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


def channel_outcomes(
    db: Session, user_id: int, notifiers: list[NotifierPlugin]
) -> list[tuple[str, str]]:
    """The ``(plugin_id, status)`` pairs one notification should produce for this user.

    The channel arithmetic on its own, with no table attached, because two kinds of
    notification now need it: a digest, whose outcomes hang off an ``alert_log`` row, and an
    admin message, whose outcomes hang off the message and the recipient (10.B12). The rule is
    identical for both, and it is the kind of rule that must not exist twice.

    In-app is resolved inline — it is local, so there is nothing to send and nothing to retry —
    and network channels start ``pending`` for the drain. When nothing is deliverable anywhere,
    the single ``skipped_no_notifier`` pair records *why* the history is the only copy.
    """
    rows: list[tuple[str, str]] = []
    for n in notifiers:
        state = resolve_state(db, n, user_id)
        if is_in_app(n.plugin_id):
            rows.append((n.plugin_id, "delivered" if state.available else "skipped"))
        elif state.active:
            rows.append((n.plugin_id, "pending"))
    if any(status in _DELIVERABLE for _, status in rows):
        return rows
    return [("", "skipped_no_notifier")]


def enqueue_deliveries(db: Session, alert_log: AlertLog, notifiers: list[NotifierPlugin]) -> None:
    """Create the ``alert_delivery`` rows for a just-written digest (7.B2). In-app is delivered
    inline (or skipped if admin-disabled); active network channels start ``pending``; if nothing
    is deliverable, one ``skipped_no_notifier`` row is written. Commits."""
    for plugin_id, status in channel_outcomes(db, alert_log.user_id, notifiers):
        db.add(_row(alert_log.id, plugin_id, status))
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


def drain_message_deliveries(db: Session, notifiers: list[NotifierPlugin]) -> int:
    """The same drain, for admin messages (10.B12). Returns the number processed.

    A near-twin of :func:`drain_deliveries` rather than a shared loop: what differs is where the
    payload comes from (a message row plus its recipient, instead of a stored digest) and which
    table records the outcome, which is most of the body. Folding them together would mean a
    function that takes a table and a payload builder — abstraction bought at the price of being
    able to read either one.
    """
    by_id = {n.plugin_id: n for n in notifiers}
    pending = list(
        db.scalars(select(AdminMessageDelivery).where(AdminMessageDelivery.status == "pending"))
    )
    for d in pending:
        plugin = by_id.get(d.plugin_id)
        message = db.get(AdminMessage, d.admin_message_id)
        if plugin is None or message is None:
            d.status = "failed"
            d.error = "notifier not loaded" if plugin is None else "message record missing"
            db.commit()
            continue
        user = db.get(User, d.user_id)
        locale = user.locale if user is not None else "en"
        try:
            plugin.send(
                message_event(message, d.user_id), merged_config(db, plugin, d.user_id), locale
            )
            d.status = "delivered"
            d.error = None
        except Exception as exc:  # includes NotifierDeliveryError after the plugin's retries
            d.status = "failed"
            d.error = str(exc)[:500]
            log.warning("message delivery failed: channel %s for user %s", d.plugin_id, d.user_id)
        db.commit()
    return len(pending)


def message_event(message: AdminMessage, user_id: int) -> TextMessageEvent:
    """The payload one recipient sees. Built on demand instead of stored per user: the message
    is immutable (ADMSG-R6), so rebuilding it can never disagree with a stored copy."""
    return TextMessageEvent(
        kind=NotificationKind.ADMIN_MESSAGE,
        user_id=user_id,
        generated_at=message.created_at,
        title=message.title,
        body=message.body,
    )


def send_test(db: Session, plugin: NotifierPlugin, user_id: int) -> None:
    """Send a test notification with the user's current merged config (NOT-R6). Synchronous, no
    persistence — used by the user (own target) and, with an admin-supplied target, by the admin.
    Propagates the plugin's error (the caller turns it into a readable API error)."""
    user = db.get(User, user_id)
    locale = user.locale if user is not None else "en"
    username = user.username if user is not None else ""
    plugin.send_test(merged_config(db, plugin, user_id), locale, username)


def in_app_visible(db: Session) -> bool:
    """Whether the in-app inbox should surface digests right now: true unless the admin has
    disabled the in-app channel (the alerts list/badge are gated on this). Defaults to true when
    no admin row exists — fail-open, never hide the source of truth."""
    return admin_enabled(db, IN_APP_PLUGIN_ID)
