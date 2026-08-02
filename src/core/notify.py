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
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core import direct_mail
from src.core.alert_engine import AlertEvent, NotificationEvent, TextMessageEvent
from src.core.contracts import NotificationKind
from src.core.models import AdminMessage, AdminMessageDelivery, AlertDelivery, AlertLog, User
from src.core.notifiers import (
    EMAIL_PLUGIN_ID,
    IN_APP_PLUGIN_ID,
    admin_enabled,
    is_in_app,
    merged_config,
    resolve_state,
)
from src.core.system_messages import resolve

if TYPE_CHECKING:
    from src.core.plugins.base import NotifierPlugin

log = logging.getLogger("wea.notifier")

_DELIVERABLE = ("delivered", "pending")

# The kinds whose `alert_log.payload_json` is a text message rather than a digest.
_TEXT_KINDS = frozenset(
    {NotificationKind.SYSTEM_MESSAGE.value, NotificationKind.ADMIN_MESSAGE.value}
)


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


def send_system_message(
    db: Session, user: User, key: str, notifiers: list[NotifierPlugin], **values: object
) -> AlertLog:
    """Write and queue one core-generated text for one user (USR-R11, 10.B16). Commits.

    The **ordinary** notification path, deliberately: a system message is a notification that
    belongs to one person, so it is an ``alert_log`` row with ``alert_delivery`` rows hanging
    off it, exactly like a digest. Routing it through the admin-message tables instead would
    have meant a broadcast machine with an audience of one, plus a column to remember that
    nobody sent it — and the in-app history is the copy that always exists (ADMSG-R2), which
    this path already guarantees.
    """
    title, body = resolve(
        db,
        key,
        locale=user.locale,
        first_name=user.first_name or user.username,
        username=user.username,
        **values,
    )
    now = datetime.now(UTC)
    event = TextMessageEvent(
        kind=NotificationKind.SYSTEM_MESSAGE,
        user_id=user.id,
        generated_at=now,
        title=title,
        body=body,
    )
    row = AlertLog(
        user_id=user.id,
        kind=NotificationKind.SYSTEM_MESSAGE.value,
        payload_json=event.model_dump(mode="json"),
        created_at=now,
    )
    db.add(row)
    db.commit()
    enqueue_deliveries(db, row, notifiers)
    return row


def send_account_notice(
    db: Session, user: User, key: str, notifiers: list[NotifierPlugin], **values: object
) -> None:
    """One of the things that happen *to* an account, told to its owner (USR-R11, 10.B26).

    Two sends on purpose, because the two halves answer to different rules. The in-app copy goes
    down the ordinary path so the note is in the history if the account ever comes back; the
    **email** goes out directly, whatever this person's notification preference says — a switch
    about price alerts is not consent to being disabled or deleted in silence, and someone who
    can no longer sign in cannot go and read the in-app copy anyway.

    Email is removed from the first send precisely so the two halves are not two copies of the
    same mail. Every other channel keeps following the preference: it is email that the account
    is *reachable at* since 10.B23, not Telegram or whatever else gets plugged in later.
    """
    others = [n for n in notifiers if n.plugin_id != EMAIL_PLUGIN_ID]
    send_system_message(db, user, key, others, **values)
    mail_account_notice(
        db,
        notifiers,
        key,
        user_id=user.id,
        first_name=user.first_name,
        username=user.username,
        address=direct_mail.address_of(user),
        locale=user.locale,
        **values,
    )


def mail_account_notice(
    db: Session,
    notifiers: list[NotifierPlugin],
    key: str,
    *,
    user_id: int,
    first_name: str,
    username: str,
    address: str,
    locale: str = "en",
    **values: object,
) -> None:
    """The email half on its own, addressed by value rather than by row (10.B26).

    Split out for the one caller that has no row left to pass: the purge sends *"your account
    has been deleted"* after the delete has committed, so the name and the address have to have
    been read beforehand — and there is no history to write the note to either.
    """
    direct_mail.send(
        db,
        direct_mail.email_channel(notifiers),
        key=key,
        user_id=user_id,
        first_name=first_name,
        username=username,
        address=address,
        now=datetime.now(UTC),
        locale=locale,
        **values,
    )


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
            # Two shapes share this table since 10.B16: a digest, and a core-generated text
            # message. The kind on the row says which, so the payload is parsed as what it is
            # instead of being guessed at from its fields.
            event: NotificationEvent = (
                TextMessageEvent.model_validate(log_row.payload_json)
                if log_row.kind in _TEXT_KINDS
                else AlertEvent.model_validate(log_row.payload_json)
            )
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
    """Probe a channel with the merged config of the admin running it (NOT-R6). Synchronous, no
    persistence. Propagates the plugin's error (the caller turns it into a readable API error).

    **Admin-only since 10.X4.** The same button used to sit on the Profile, from the days when a
    user typed their own delivery address into it. Since 10.B23/10.B25 there is nothing personal
    left to test — the address is the account, and it has already proved itself by carrying the
    password the person signed in with. What remains is the question this probe really answers,
    *"does the server's SMTP config work"*, and that one belongs to whoever configured it.
    """
    user = db.get(User, user_id)
    locale = user.locale if user is not None else "en"
    username = user.username if user is not None else ""
    plugin.send_test(merged_config(db, plugin, user_id), locale, username)


def in_app_visible(db: Session) -> bool:
    """Whether the in-app inbox should surface digests right now: true unless the admin has
    disabled the in-app channel (the alerts list/badge are gated on this). Defaults to true when
    no admin row exists — fail-open, never hide the source of truth."""
    return admin_enabled(db, IN_APP_PLUGIN_ID)
