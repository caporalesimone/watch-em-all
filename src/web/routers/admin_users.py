"""Admin user management (user-management.md). MVP: create + list.

Every route is admin-only (require_admin via AdminDep). The richer lifecycle —
reset password, disable/enable, deferred soft-delete with a grace period and
restore, status filters, last-login sort, courtesy notifications — lands in
phase 10. There is no self-registration: accounts exist only because an admin
created them (USR-R1).
"""

from __future__ import annotations

from fastapi import APIRouter, status
from sqlalchemy import select

from src.core.errors import APIError
from src.core.models import User
from src.core.security import hash_password
from src.web.deps import AdminDep, SessionDep
from src.web.schemas import AdminUserSummary, UserCreate

router = APIRouter(prefix="/admin", tags=["Admin: users"])


def _to_summary(user: User) -> AdminUserSummary:
    return AdminUserSummary(
        id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        role=user.role,
        is_active=user.is_active,
        must_change_password=user.must_change_password,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
    )


@router.get(
    "/users",
    response_model=list[AdminUserSummary],
    summary="List all accounts (admin only).",
)
def list_users(_admin: AdminDep, db: SessionDep) -> list[AdminUserSummary]:
    users = db.scalars(select(User).order_by(User.username)).all()
    return [_to_summary(u) for u in users]


@router.post(
    "/users",
    response_model=AdminUserSummary,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account with a temporary password + forced first change (admin only).",
)
def create_user(body: UserCreate, _admin: AdminDep, db: SessionDep) -> AdminUserSummary:
    if db.scalar(select(User.id).where(User.username == body.username)) is not None:
        raise APIError(409, "username_taken", "that username is already in use")
    user = User(
        username=body.username,
        first_name=body.first_name,
        last_name=body.last_name,
        password_hash=hash_password(body.temp_password),
        role=body.role,
        is_active=True,
        must_change_password=True,  # USR-R2: forced change at first login
    )
    db.add(user)
    db.commit()
    db.refresh(user)  # load server-side defaults (id, created_at)
    return _to_summary(user)
