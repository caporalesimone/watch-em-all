"""Alert history API (endpoints.md, alert-engine.md). Phase 6 (6.B8).

The user's in-app notification history: a paginated list with read/unread state, the full
digest detail, a mark-read action and the unread count for the dashboard badge. Per-user
(DB-R1). Per-channel delivery outcomes arrive with the channels in phase 7.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Query
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select

from src.core.admin_messages import unread_broadcast_count
from src.core.contracts import NotificationKind
from src.core.errors import APIError
from src.core.models import AdminMessage, AdminMessageDelivery, AlertDelivery, AlertLog, User
from src.core.notify import in_app_visible, message_event
from src.web.deps import SessionDep, UserDep
from src.web.schemas import (
    AlertDeliveryOut,
    AlertDetail,
    AlertIdsBody,
    AlertListItem,
    AlertPage,
    UnreadCount,
)

router = APIRouter(prefix="/alerts", tags=["Alerts"])


def _owned(db: SessionDep, user: UserDep, alert_id: int) -> AlertLog:
    row = db.scalar(select(AlertLog).where(AlertLog.id == alert_id, AlertLog.user_id == user.sub))
    if row is None:
        raise APIError(404, "alert_not_found", "alert not found")
    return row


def _cart_count(row: AlertLog) -> int:
    carts = row.payload_json.get("cart_alerts") if isinstance(row.payload_json, dict) else None
    return len(carts) if isinstance(carts, list) else 0


@router.get("", response_model=AlertPage, summary="List the user's alert history (paginated).")
def list_alerts(
    user: UserDep,
    db: SessionDep,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    kind: str | None = Query(None),
) -> AlertPage:
    if not in_app_visible(db):  # admin disabled the in-app channel → inbox hidden for everyone
        return AlertPage(items=[], total=0, page=page, page_size=page_size)
    where = [AlertLog.user_id == user.sub]
    if kind is not None:
        where.append(AlertLog.kind == kind)
    total = db.scalar(select(func.count()).select_from(AlertLog).where(*where)) or 0
    take = page * page_size  # enough of each source to fill this page after the merge
    items = [
        AlertListItem(
            id=r.id,
            source="alert",
            kind=r.kind,
            created_at=r.created_at,
            read=r.read_at is not None,
            cart_count=_cart_count(r),
        )
        for r in db.scalars(
            select(AlertLog)
            .where(*where)
            .order_by(AlertLog.created_at.desc(), AlertLog.id.desc())
            .limit(take)
        ).all()
    ]

    # The second source (10.B12). Broadcasts live in their own table — one row for everybody —
    # so the history is a union rather than a query, and the merge happens here in Python. It
    # can afford to: the nightly purge caps a user's alert rows and announcements are rare, so
    # both sides are short lists. A SQL union would buy nothing and cost the read.
    person = db.get(User, user.sub)
    if person is not None and kind in (None, NotificationKind.ADMIN_MESSAGE.value):
        pointer = person.last_broadcast_read_id
        broadcasts = db.scalars(
            select(AdminMessage)
            .where(AdminMessage.audience == "all")
            .order_by(AdminMessage.created_at.desc(), AdminMessage.id.desc())
            .limit(take)
        ).all()
        total += _broadcast_total(db)
        items += [
            AlertListItem(
                id=b.id,
                source="broadcast",
                kind=NotificationKind.ADMIN_MESSAGE.value,
                created_at=b.created_at,
                # Read state is the pointer, not a flag: "read up to N" (see mark_broadcast_read).
                read=pointer is not None and b.id <= pointer,
                cart_count=0,
            )
            for b in broadcasts
        ]

    items.sort(key=lambda i: (i.created_at, i.id), reverse=True)
    start = (page - 1) * page_size
    return AlertPage(
        items=items[start : start + page_size], total=total, page=page, page_size=page_size
    )


def _broadcast_total(db: SessionDep) -> int:
    return int(
        db.scalar(
            select(func.count()).select_from(AdminMessage).where(AdminMessage.audience == "all")
        )
        or 0
    )


@router.get("/unread-count", response_model=UnreadCount, summary="Unread count for the badge.")
def unread_count(user: UserDep, db: SessionDep) -> UnreadCount:
    if not in_app_visible(db):  # in-app channel disabled by the admin → no badge
        return UnreadCount(count=0)
    count = (
        db.scalar(
            select(func.count())
            .select_from(AlertLog)
            .where(AlertLog.user_id == user.sub, AlertLog.read_at.is_(None))
        )
        or 0
    )
    # The second source (10.B12). A broadcast has no row of its own per user, so its unread
    # state is the gap between the pointer and the newest announcement — the read-side price of
    # writing one row instead of N.
    row = db.get(User, user.sub)
    if row is not None:
        count += unread_broadcast_count(db, row)
    return UnreadCount(count=count)


@router.get(
    "/broadcasts/{message_id}",
    response_model=AlertDetail,
    summary="One announcement in full, with this user's own delivery outcomes.",
)
def get_broadcast(message_id: int, user: UserDep, db: SessionDep) -> AlertDetail:
    if not in_app_visible(db):
        raise APIError(404, "alert_not_found", "alert not found")
    message = db.get(AdminMessage, message_id)
    if message is None or message.audience != "all":
        raise APIError(404, "alert_not_found", "alert not found")
    person = db.get(User, user.sub)
    pointer = person.last_broadcast_read_id if person is not None else None
    deliveries = [
        AlertDeliveryOut(
            plugin_id=d.plugin_id, status=d.status, error=d.error, updated_at=d.updated_at
        )
        # Only this person's rows: the message is shared, the delivery is not (DB-R1).
        for d in db.scalars(
            select(AdminMessageDelivery)
            .where(
                AdminMessageDelivery.admin_message_id == message.id,
                AdminMessageDelivery.user_id == user.sub,
            )
            .order_by(AdminMessageDelivery.id)
        ).all()
    ]
    return AlertDetail(
        id=message.id,
        source="broadcast",
        kind=NotificationKind.ADMIN_MESSAGE.value,
        created_at=message.created_at,
        read=pointer is not None and message.id <= pointer,
        payload=message_event(message, user.sub).model_dump(mode="json"),
        deliveries=deliveries,
    )


@router.post(
    "/broadcasts/{message_id}/read",
    status_code=204,
    summary="Mark announcements read up to this one (the pointer only moves forward).",
)
def mark_broadcast_read(message_id: int, user: UserDep, db: SessionDep) -> None:
    """Advance the pointer, never rewind it.

    Reading is **monotone** here, and deliberately so: "read up to N" is the only sentence a
    pointer can say, so marking a recent announcement read also clears the older ones. That is
    the accepted trade of the single-row design — and it is the right shape for announcements,
    where the newest one is the one that matters, while alerts keep their per-row read state
    precisely because there it would be wrong.
    """
    row = db.get(User, user.sub)
    if row is None:
        raise APIError(404, "alert_not_found", "alert not found")
    if row.last_broadcast_read_id is None or message_id > row.last_broadcast_read_id:
        row.last_broadcast_read_id = message_id
        db.commit()


@router.delete("", status_code=204, summary="Delete the user's alerts by id (bulk).")
def delete_alerts(body: AlertIdsBody, user: UserDep, db: SessionDep) -> None:
    # Scoped to the caller's own rows (DB-R1); ids they don't own are simply not matched.
    db.execute(sa_delete(AlertLog).where(AlertLog.user_id == user.sub, AlertLog.id.in_(body.ids)))
    db.commit()


@router.get("/{alert_id}", response_model=AlertDetail, summary="One notification in full.")
def get_alert(alert_id: int, user: UserDep, db: SessionDep) -> AlertDetail:
    if not in_app_visible(db):  # in-app channel disabled by the admin → inbox hidden
        raise APIError(404, "alert_not_found", "alert not found")
    row = _owned(db, user, alert_id)
    deliveries = [
        AlertDeliveryOut(
            plugin_id=d.plugin_id, status=d.status, error=d.error, updated_at=d.updated_at
        )
        for d in db.scalars(
            select(AlertDelivery)
            .where(AlertDelivery.alert_log_id == row.id)
            .order_by(AlertDelivery.id)
        ).all()
    ]
    return AlertDetail(
        id=row.id,
        kind=row.kind,
        created_at=row.created_at,
        read=row.read_at is not None,
        payload=row.payload_json,
        deliveries=deliveries,
    )


@router.post("/{alert_id}/read", status_code=204, summary="Mark a notification as read.")
def mark_read(alert_id: int, user: UserDep, db: SessionDep) -> None:
    row = _owned(db, user, alert_id)
    if row.read_at is None:  # idempotent: re-reading keeps the first timestamp
        row.read_at = datetime.now(UTC)
        db.commit()
