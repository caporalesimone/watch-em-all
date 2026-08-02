"""Sending an admin message (admin-notifications.md, ADMSG-R1/R2). Phase 10 (10.B12).

One entry point, :func:`send_admin_message`, because the two shapes a message can take differ
only in who receives it — and the difference is worth stating once, here, rather than in every
caller:

**A broadcast writes one row.** The message itself is the record, and each user carries a
pointer to the last announcement they have read (``users.last_broadcast_read_id``). This is
Simone's decision of 2026-08-02 and it buys the obvious thing — an announcement costs the same
whether the installation has three accounts or three thousand — at a price paid on the read
side: the unread badge becomes a sum of two sources and the history a union. Read state also
becomes **monotone**, since "read up to N" is the only sentence a pointer can say. That is
right for announcements and wrong for alerts, which is exactly why the two mechanisms stay
apart instead of being unified.

**A message to one user takes the ordinary path**: it has a single recipient already, so it
lands in that user's ``alert_log`` like any other notification and the pointer never enters
into it.

Delivery outcomes are per recipient either way (ADMSG-R2), so both shapes write N rows in
``admin_message_delivery`` — that is the part a pointer cannot compress, because whether the
email arrived is a fact about a person, not about the message.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.core.contracts import NotificationKind
from src.core.models import AdminMessage, AdminMessageDelivery, AlertLog, User
from src.core.notify import channel_outcomes, message_event

if TYPE_CHECKING:
    from src.core.plugins.base import NotifierPlugin


def recipients(db: Session, target_user_id: int | None) -> list[User]:
    """Who the message goes to: one named user, or every account that can still sign in.

    A broadcast deliberately skips disabled accounts and accounts marked for deletion — sending
    an announcement to someone who cannot log in to read it is filling an inbox nobody will
    open. A *targeted* message has no such filter: telling one person that their account is on
    its way out is precisely the case ADMSG-R1 exists for.
    """
    if target_user_id is not None:
        user = db.get(User, target_user_id)
        return [user] if user is not None else []
    return list(
        db.scalars(
            select(User)
            .where(User.is_active.is_(True), User.deletion_marked_at.is_(None))
            .order_by(User.id)
        ).all()
    )


def send_admin_message(
    db: Session,
    *,
    sender_id: int | None,
    title: str,
    body: str,
    target_user_id: int | None,
    notifiers: list[NotifierPlugin],
) -> AdminMessage:
    """Persist the message, record its in-app trace and queue its deliveries. Commits.

    The network channels are left ``pending`` for the worker drain rather than sent here: the
    admin gets an answer as soon as the message is *recorded*, which is the part that cannot be
    lost, and a slow SMTP server never turns "send announcement" into a request that times out.
    """
    people = recipients(db, target_user_id)
    message = AdminMessage(
        sender_id=sender_id,
        audience="user" if target_user_id is not None else "all",
        target_user_id=target_user_id,
        title=title,
        body=body,
        recipient_count=len(people),
    )
    db.add(message)
    db.flush()  # the id the delivery rows and the alert_log trace both need

    now = datetime.now(UTC)
    for user in people:
        if target_user_id is not None:
            # One recipient → the ordinary history row, so it sorts, filters and marks read like
            # every other notification the user has.
            db.add(
                AlertLog(
                    user_id=user.id,
                    kind=NotificationKind.ADMIN_MESSAGE.value,
                    admin_message_id=message.id,
                    payload_json=message_event(message, user.id).model_dump(mode="json"),
                    created_at=now,
                )
            )
        for plugin_id, status in channel_outcomes(db, user.id, notifiers):
            db.add(
                AdminMessageDelivery(
                    admin_message_id=message.id,
                    user_id=user.id,
                    plugin_id=plugin_id,
                    status=status,
                )
            )
    db.commit()
    return message


def latest_broadcast_id(db: Session) -> int | None:
    """The newest announcement, or None if none was ever sent.

    Used to **initialise** a new account's pointer (see :func:`start_pointer_at_latest`): an
    announcement is addressed to the people who were there, and an account created today should
    not open onto a year of old notices. Doing it by id rather than by comparing timestamps is
    deliberate — a date bound looked equivalent and was not, because SQLite compares stored
    timestamps as text and a bound Python ``datetime`` carries microseconds the stored
    ``CURRENT_TIMESTAMP`` does not. The id is an id on every engine.
    """
    return db.scalar(select(func.max(AdminMessage.id)))


def unread_broadcast_count(db: Session, user: User) -> int:
    """How many announcements this user has not reached yet: everything after their pointer.

    Only broadcasts — a targeted message already has its own ``alert_log`` row and is counted
    there, and counting it twice is the failure mode this split invites.
    """
    where = [AdminMessage.audience == "all"]
    if user.last_broadcast_read_id is not None:
        where.append(AdminMessage.id > user.last_broadcast_read_id)
    return int(db.scalar(select(func.count()).select_from(AdminMessage).where(*where)) or 0)
