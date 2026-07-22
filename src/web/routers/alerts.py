"""Alert history API (endpoints.md, alert-engine.md). Phase 6 (6.B8).

The user's in-app notification history: a paginated list with read/unread state, the full
digest detail, a mark-read action and the unread count for the dashboard badge. Per-user
(DB-R1). Per-channel delivery outcomes arrive with the channels in phase 7.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from src.core.errors import APIError
from src.core.models import AlertLog
from src.web.deps import SessionDep, UserDep
from src.web.schemas import AlertDetail, AlertListItem, AlertPage, UnreadCount

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
    where = [AlertLog.user_id == user.sub]
    if kind is not None:
        where.append(AlertLog.kind == kind)
    total = db.scalar(select(func.count()).select_from(AlertLog).where(*where)) or 0
    rows = db.scalars(
        select(AlertLog)
        .where(*where)
        .order_by(AlertLog.created_at.desc(), AlertLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    items = [
        AlertListItem(
            id=r.id,
            kind=r.kind,
            created_at=r.created_at,
            read=r.read_at is not None,
            cart_count=_cart_count(r),
        )
        for r in rows
    ]
    return AlertPage(items=items, total=total, page=page, page_size=page_size)


@router.get("/unread-count", response_model=UnreadCount, summary="Unread count for the badge.")
def unread_count(user: UserDep, db: SessionDep) -> UnreadCount:
    count = (
        db.scalar(
            select(func.count())
            .select_from(AlertLog)
            .where(AlertLog.user_id == user.sub, AlertLog.read_at.is_(None))
        )
        or 0
    )
    return UnreadCount(count=count)


@router.get("/{alert_id}", response_model=AlertDetail, summary="One notification in full.")
def get_alert(alert_id: int, user: UserDep, db: SessionDep) -> AlertDetail:
    row = _owned(db, user, alert_id)
    return AlertDetail(
        id=row.id,
        kind=row.kind,
        created_at=row.created_at,
        read=row.read_at is not None,
        payload=row.payload_json,
        deliveries=[],  # per-channel outcomes arrive in phase 7
    )


@router.post("/{alert_id}/read", status_code=204, summary="Mark a notification as read.")
def mark_read(alert_id: int, user: UserDep, db: SessionDep) -> None:
    row = _owned(db, user, alert_id)
    if row.read_at is None:  # idempotent: re-reading keeps the first timestamp
        row.read_at = datetime.now(UTC)
        db.commit()
