"""Admin messages API (admin-notifications.md, ADMSG-R1/R2). Phase 10 (10.B12).

Composing is the whole endpoint: title, Markdown body, and either everybody or one named
person. There is no edit and no recall (ADMSG-R6) — a message that has already reached an inbox
cannot be unsent, so the honest correction is another message.

The reach of the send lives in the core ([admin_messages](../../core/admin_messages.py)); this
module is the HTTP shape around it, plus the one refusal worth making here: a message addressed
to an account that does not exist is a mistake, not an empty broadcast.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from src.core.admin_messages import send_admin_message
from src.core.errors import APIError
from src.core.models import AdminMessage, User
from src.core.plugins.base import NotifierPlugin
from src.web.deps import AdminDep, SessionDep
from src.web.schemas import AdminMessageCreate, AdminMessageOut

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
