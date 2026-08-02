"""Admin messages API (admin-notifications.md, ADMSG-R1/R2). Phase 10 (10.B12).

Composing is the whole endpoint: title, Markdown body, and either everybody or one named
person. There is no edit and no recall (ADMSG-R6) — a message that has already reached an inbox
cannot be unsent, so the honest correction is another message.

The reach of the send lives in the core ([admin_messages](../../core/admin_messages.py)); this
module is the HTTP shape around it, plus the one refusal worth making here: a message addressed
to an account that does not exist is a mistake, not an empty broadcast.

Reading back (10.B13) shows **delivery per recipient** (ADMSG-R5): which channel took it for
which person, and why one failed. Since 10.B30 it also reports **how many** have opened it —
an aggregate, never a name. The distinction is the whole of the rule: *"twelve of twenty read
this"* is a fact about a message, *"Alice read it and Bob did not"* is a fact about Alice, and
only the first belongs to the sender. The per-recipient view below therefore still carries
delivery alone, and there is no query here that could produce the second.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request
from sqlalchemy import distinct, func, select

from src.core.admin_messages import send_admin_message
from src.core.errors import APIError
from src.core.markdown import to_html
from src.core.models import AdminMessage, AdminMessageDelivery, AlertLog, User
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
    MessagePreviewOut,
    MessagePreviewRequest,
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


def _read_counts(db: SessionDep, messages: list[AdminMessage]) -> dict[int, int]:
    """How many recipients have opened each message in the app (10.B30).

    **Two grouped queries for a whole page**, never one per row — the same rule `_counts` above
    already follows. Nothing here is worse than linear in the rows it touches:

    - a **targeted** message has an ``alert_log`` row of its own carrying ``admin_message_id``,
      so read is that row's ``read_at``. One ``GROUP BY`` over a table the nightly purge keeps
      short (``alert_keep_last``).
    - a **broadcast** has no per-user row: reading is the pointer ``last_broadcast_read_id``, so
      a recipient has read announcement *M* when their pointer has reached *M*'s id. The
      recipients are the delivery rows — indexed on ``admin_message_id`` — joined to their user
      by primary key.

    Restricting to the delivery rows is not a detail: an account created **after** an
    announcement starts its pointer at the newest id (``latest_broadcast_id``), so "pointer ≥ id"
    over all users would count somebody who never received it as having read it.

    A recipient who deletes the message without opening it simply never appears here, which is
    the answer to *"what if they delete it unread"* — it counts as unread, as it should.
    """
    out = {m.id: 0 for m in messages}
    targeted = [m.id for m in messages if m.audience != "all"]
    broadcasts = [m.id for m in messages if m.audience == "all"]

    if targeted:
        for message_id, n in db.execute(
            select(AlertLog.admin_message_id, func.count())
            .where(AlertLog.admin_message_id.in_(targeted), AlertLog.read_at.is_not(None))
            .group_by(AlertLog.admin_message_id)
        ).all():
            out[int(message_id)] = int(n)

    if broadcasts:
        for message_id, n in db.execute(
            select(
                AdminMessageDelivery.admin_message_id,
                func.count(distinct(AdminMessageDelivery.user_id)),
            )
            .join(User, User.id == AdminMessageDelivery.user_id)
            .where(
                AdminMessageDelivery.admin_message_id.in_(broadcasts),
                User.last_broadcast_read_id.is_not(None),
                User.last_broadcast_read_id >= AdminMessageDelivery.admin_message_id,
            )
            .group_by(AdminMessageDelivery.admin_message_id)
        ).all():
            out[int(message_id)] = int(n)
    return out


def _summary(
    db: SessionDep, message: AdminMessage, counts: MessageOutcomeCounts, read_count: int = 0
) -> AdminMessageSummary:
    sender = db.get(User, message.sender_id) if message.sender_id else None
    return AdminMessageSummary(
        **_out(db, message).model_dump(),
        sender_username=sender.username if sender else None,
        outcomes=counts,
        read_count=read_count,
    )


@router.post(
    "/preview",
    response_model=MessagePreviewOut,
    summary="Render a draft body exactly as the recipients will see it (admin only).",
)
def preview(body: MessagePreviewRequest, _admin: AdminDep) -> MessagePreviewOut:
    """The editor's Preview tab, answered by the renderer that does the real job.

    A round trip instead of markdown-it in the browser, and the reason is the requirement
    itself: the preview has to be *identical* to what gets delivered. Two renderers can only be
    made to agree, and 9.F8 is the local proof that agreement decays — the Difference rule lived
    in Python and in TypeScript until they stopped matching. One renderer, and the question
    cannot arise.

    Called on the tab switch, not on every keystroke (Simone's call, 2026-08-02): a preview a
    person asks for is worth one request; a preview that renders itself while they type is worth
    a few hundred.
    """
    return MessagePreviewOut(body_html=to_html(body.body))


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
    audience: Annotated[Literal["all", "user"] | None, Query()] = None,
) -> AdminMessagePage:
    # The filter separates the two things this list mixes (10.F30): an announcement to everybody
    # and a note to one person are the same table but not the same job, and looking for one of
    # them among the other is most of what this page is used for.
    where = [AdminMessage.audience == audience] if audience is not None else []
    total = int(db.scalar(select(func.count()).select_from(AdminMessage).where(*where)) or 0)
    rows = list(
        db.scalars(
            select(AdminMessage)
            .where(*where)
            .order_by(AdminMessage.created_at.desc(), AdminMessage.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    counts = _counts(db, [m.id for m in rows])
    reads = _read_counts(db, rows)
    return AdminMessagePage(
        items=[_summary(db, m, counts[m.id], reads[m.id]) for m in rows],
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
    read_count = _read_counts(db, [message])[message_id]
    return AdminMessageDetail(
        **_summary(db, message, counts, read_count).model_dump(), recipients=recipients
    )


@router.delete(
    "/{message_id}",
    status_code=204,
    summary="Remove a sent message from the history (admin only).",
)
def delete_message(message_id: int, _admin: AdminDep, db: SessionDep) -> None:
    """Delete the record of a message, and — for a broadcast — the message itself (10.B29).

    **This is not an un-send** (ADMSG-R6 stands): what it removes is history, and how much of it
    depends on where that history lives. A **broadcast** is one row for everybody, so deleting it
    takes it out of every recipient's list as well — which is the point, since a user cannot
    delete an announcement themselves. A **targeted** message also gave its recipient an
    ``alert_log`` row of their own: that one is theirs, it stays, and they can delete it. The
    delivery outcomes go either way, by cascade.

    Nothing here reaches into somebody else's inbox to retract what they already read on another
    channel. A mail that has been sent is sent.
    """
    message = db.get(AdminMessage, message_id)
    if message is None:
        raise APIError(404, "message_not_found", "no such message")
    db.delete(message)
    db.commit()


@router.post(
    "",
    response_model=AdminMessageOut,
    status_code=201,
    summary="Send a message to every active account or to one user (admin only).",
)
def create_message(
    body: AdminMessageCreate, request: Request, admin: AdminDep, db: SessionDep
) -> AdminMessageOut:
    if body.target_user_id is not None:
        target = db.get(User, body.target_user_id)
        if target is None:
            raise APIError(404, "user_not_found", "no such user")
        # Admins are not an audience for this channel, themselves least of all (Simone's rule,
        # 2026-08-02). Refused here and not merely hidden from the composer's dropdown: a rule
        # enforced by a widget is a rule the API does not have.
        if target.role == "admin":
            raise APIError(422, "recipient_is_admin", "administrators do not receive messages")
    message = send_admin_message(
        db,
        sender_id=admin.sub,
        title=body.title.strip(),
        body=body.body,
        target_user_id=body.target_user_id,
        notifiers=_notifiers(request),
    )
    return _out(db, message)
