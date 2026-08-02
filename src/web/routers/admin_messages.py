"""Admin messages API (admin-notifications.md, ADMSG-R1/R2). Phase 10 (10.B12).

Composing is the whole endpoint: title, Markdown body, and either everybody or one named
person. There is no edit and no recall (ADMSG-R6) — a message that has already reached an inbox
cannot be unsent, so the honest correction is another message.

The reach of the send lives in the core ([admin_messages](../../core/admin_messages.py)); this
module is the HTTP shape around it, plus the one refusal worth making here: a message addressed
to an account that does not exist is a mistake, not an empty broadcast.

Reading back (10.B13) shows **delivery and only delivery** (ADMSG-R5): which channel took it
for which recipient, and why one failed. Whether anybody opened it does not appear, and there
is no query here that could produce it.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request
from sqlalchemy import func, select

from src.core.admin_messages import send_admin_message
from src.core.errors import APIError
from src.core.models import AdminMessage, AdminMessageDelivery, User
from src.core.plugins.base import NotifierPlugin
from src.web.deps import AdminDep, SessionDep
from src.web.schemas import (
    AdminMessageCreate,
    AdminMessageDetail,
    AdminMessageOut,
    AdminMessagePage,
    AdminMessageSummary,
    AlertDeliveryOut,
    MessageOutcomeCounts,
    MessageRecipientOut,
)

router = APIRouter(prefix="/admin/messages", tags=["Admin: messages"])


def _notifiers(request: Request) -> list[NotifierPlugin]:
    loaded = list(getattr(request.app.state, "loaded_plugins", []))
    return [lp.plugin for lp in loaded if isinstance(lp.plugin, NotifierPlugin)]


def _out(db: SessionDep, message: AdminMessage) -> AdminMessageOut:
    target = db.get(User, message.target_user_id) if message.target_user_id else None
    return AdminMessageOut(
        id=message.id,
        audience=message.audience,
        target_user_id=message.target_user_id,
        target_username=target.username if target else None,
        title=message.title,
        body=message.body,
        recipient_count=message.recipient_count,
        created_at=message.created_at,
    )


def _counts(db: SessionDep, message_ids: list[int]) -> dict[int, MessageOutcomeCounts]:
    """Delivery tallies for a set of messages, in one query rather than one per row."""
    tally: dict[int, MessageOutcomeCounts] = {mid: MessageOutcomeCounts() for mid in message_ids}
    if not message_ids:
        return tally
    rows = db.execute(
        select(
            AdminMessageDelivery.admin_message_id,
            AdminMessageDelivery.status,
            func.count(),
        )
        .where(AdminMessageDelivery.admin_message_id.in_(message_ids))
        .group_by(AdminMessageDelivery.admin_message_id, AdminMessageDelivery.status)
    ).all()
    for message_id, status, n in rows:
        # `skipped_no_notifier` folds into `skipped`: for the admin they are the same fact —
        # nothing left the building, the person has it in-app only.
        bucket = "skipped" if str(status).startswith("skipped") else str(status)
        if hasattr(tally[message_id], bucket):
            setattr(tally[message_id], bucket, getattr(tally[message_id], bucket) + int(n))
    return tally


def _summary(
    db: SessionDep, message: AdminMessage, counts: MessageOutcomeCounts
) -> AdminMessageSummary:
    sender = db.get(User, message.sender_id) if message.sender_id else None
    return AdminMessageSummary(
        **_out(db, message).model_dump(),
        sender_username=sender.username if sender else None,
        outcomes=counts,
    )


@router.get(
    "",
    response_model=AdminMessagePage,
    summary="Messages sent, newest first, with delivery outcomes (admin only).",
)
def list_messages(
    _admin: AdminDep,
    db: SessionDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AdminMessagePage:
    total = int(db.scalar(select(func.count()).select_from(AdminMessage)) or 0)
    rows = list(
        db.scalars(
            select(AdminMessage)
            .order_by(AdminMessage.created_at.desc(), AdminMessage.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    counts = _counts(db, [m.id for m in rows])
    return AdminMessagePage(
        items=[_summary(db, m, counts[m.id]) for m in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{message_id}",
    response_model=AdminMessageDetail,
    summary="One message with its per-recipient, per-channel outcomes (admin only).",
)
def get_message(message_id: int, _admin: AdminDep, db: SessionDep) -> AdminMessageDetail:
    message = db.get(AdminMessage, message_id)
    if message is None:
        raise APIError(404, "message_not_found", "no such message")

    # Left join on the user: an account deleted since the send leaves its outcome rows behind
    # only until the cascade removes them, but a message row that outlives its recipient must
    # still render rather than 500.
    rows = db.execute(
        select(AdminMessageDelivery, User.username)
        .join(User, User.id == AdminMessageDelivery.user_id, isouter=True)
        .where(AdminMessageDelivery.admin_message_id == message_id)
        .order_by(AdminMessageDelivery.user_id, AdminMessageDelivery.id)
    ).all()

    by_user: dict[int, MessageRecipientOut] = {}
    for delivery, username in rows:
        person = by_user.setdefault(
            delivery.user_id,
            MessageRecipientOut(user_id=delivery.user_id, username=username or "—"),
        )
        person.channels.append(
            AlertDeliveryOut(
                plugin_id=delivery.plugin_id,
                status=delivery.status,
                error=delivery.error,
                updated_at=delivery.updated_at,
            )
        )

    # Failures first: an admin opens this page to find out what went wrong, and the accounts it
    # reached fine are the part they can scroll past.
    recipients = sorted(
        by_user.values(),
        key=lambda r: (not any(c.status == "failed" for c in r.channels), r.username),
    )
    counts = _counts(db, [message_id])[message_id]
    return AdminMessageDetail(**_summary(db, message, counts).model_dump(), recipients=recipients)


@router.post(
    "",
    response_model=AdminMessageOut,
    status_code=201,
    summary="Send a message to every active account or to one user (admin only).",
)
def create_message(
    body: AdminMessageCreate, request: Request, admin: AdminDep, db: SessionDep
) -> AdminMessageOut:
    if body.target_user_id is not None and db.get(User, body.target_user_id) is None:
        raise APIError(404, "user_not_found", "no such user")
    message = send_admin_message(
        db,
        sender_id=admin.sub,
        title=body.title.strip(),
        body=body.body,
        target_user_id=body.target_user_id,
        notifiers=_notifiers(request),
    )
    return _out(db, message)
