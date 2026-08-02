"""Admin user management (user-management.md): create, list, reset, enable/disable.

Every route is admin-only (require_admin via AdminDep). The deferred soft-delete with its
grace period and restore is 10.B3; the courtesy notification that goes with it now arrives
from the system-message catalog (10.B16) — the wording lives there, this module only says
when to send it. There is no self-registration: accounts exist only because an admin created
them (USR-R1).

**An admin never acts on their own account** (10.B1, Simone 2026-08-02). Disabling — and
later deleting — yourself is refused server-side: with a single administrator it is a
lockout with no way back through the application, only through the database. The guard
looks at *who is asking*, not at the target's role, so an admin may freely create, disable
and delete **other** admins. Resetting your own password is not guarded: you pick the new
one, so it locks nobody out.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Request, status
from sqlalchemy import nullsfirst, nullslast, select
from sqlalchemy.sql.elements import UnaryExpression

from src.core import credentials as cred
from src.core import notifiers as notif
from src.core import system_messages as sysmsg
from src.core.admin_messages import latest_broadcast_id
from src.core.errors import APIError
from src.core.models import User
from src.core.notifiers import EMAIL_PLUGIN_ID
from src.core.notify import send_system_message
from src.core.plugins.base import NotifierPlugin
from src.core.security import generate_password, hash_password
from src.core.settings import get_system_settings
from src.web.deps import AdminDep, SessionDep
from src.web.schemas import AdminUserPatch, AdminUserSummary, UserCreate

log = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["Admin: users"])


def _target(db: SessionDep, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise APIError(404, "user_not_found", "no such account")
    return user


def _notifiers(request: Request) -> list[NotifierPlugin]:
    loaded = list(getattr(request.app.state, "loaded_plugins", []))
    return [lp.plugin for lp in loaded if isinstance(lp.plugin, NotifierPlugin)]


def _mail_password(
    request: Request,
    db: SessionDep,
    key: str,
    *,
    first_name: str,
    address: str,
    user_id: int,
) -> str:
    """Generate a password, put it in front of its owner, and hand it back to be hashed (10.B24).

    Both refusals are deliberate and both happen **before** anything is written. A channel that
    cannot deliver is a 422 — this is a precondition of the operation, not a server fault, and
    the administrator can fix it on the Notifiers page. A channel that accepted the job and then
    failed is a 502: nothing the caller did was wrong, and the account is untouched either way.
    """
    plugin = cred.email_channel(_notifiers(request))
    if not cred.channel_ready(db, plugin):
        raise APIError(
            422,
            "email_channel_unavailable",
            "the email channel is off or not configured, so no password can be delivered",
        )
    password = generate_password()
    try:
        cred.send_password(
            db,
            plugin,
            key=key,
            user_id=user_id,
            first_name=first_name,
            address=address,
            password=password,
            now=datetime.now(tz=UTC),
        )
    except cred.CredentialMailError as exc:
        raise APIError(
            502, "password_email_failed", f"the password could not be sent: {exc}"
        ) from exc
    return password


def _courtesy(request: Request, db: SessionDep, user: User, key: str, **values: object) -> None:
    """Tell somebody what has just happened to their account (USR-R11, 10.B16).

    **Best-effort, and after the commit.** The account state is the operation; the courtesy note
    is a consequence of it. An administrator who disables an account must not see the request
    fail — leaving them unsure whether it took — because a notifier was unreachable. The in-app
    row is written first and is the copy that always exists, so nothing is lost either way:
    somebody restored later finds the note waiting in their history.
    """
    try:
        send_system_message(db, user, key, _notifiers(request), **values)
    except Exception:  # noqa: BLE001 — a notification must never undo the thing it describes
        log.warning("courtesy notification %s failed for user %s", key, user.id, exc_info=True)


def _refuse_self(admin_id: int, target: User) -> None:
    """The one thing an administrator may not do to themselves (10.B1)."""
    if target.id == admin_id:
        raise APIError(403, "cannot_target_self", "an admin cannot disable or delete themselves")


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
        deletion_marked_at=user.deletion_marked_at,
        deletion_due_at=user.deletion_due_at,
    )


@router.get(
    "/users",
    response_model=list[AdminUserSummary],
    summary="List all accounts (admin only).",
)
def list_users(
    _admin: AdminDep,
    db: SessionDep,
    status_filter: Annotated[
        Literal["active", "disabled", "deleting"] | None, Query(alias="status")
    ] = None,
    sort: Literal["username", "last_login"] = "username",
    order: Literal["asc", "desc"] = "asc",
) -> list[AdminUserSummary]:
    stmt = select(User)
    # "Being deleted" is not a column but the combination the login gate already reads
    # (USR-R14): an account marked for deletion is out whatever `is_active` says, so it must
    # not also show up under "disabled" or the two filters would overlap.
    if status_filter == "deleting":
        stmt = stmt.where(User.deletion_marked_at.is_not(None))
    elif status_filter == "active":
        stmt = stmt.where(User.is_active.is_(True), User.deletion_marked_at.is_(None))
    elif status_filter == "disabled":
        stmt = stmt.where(User.is_active.is_(False), User.deletion_marked_at.is_(None))

    ordering: UnaryExpression[Any]
    if sort == "last_login":
        column = User.last_login_at
        # Never signed in is the far end of dormant, not a missing value to sweep aside:
        # ascending (longest idle first) it belongs at the top, descending at the bottom.
        # The database default does the opposite, so both ends are stated explicitly.
        ordering = nullsfirst(column.asc()) if order == "asc" else nullslast(column.desc())
    else:
        ordering = User.username.asc() if order == "asc" else User.username.desc()

    users = db.scalars(stmt.order_by(ordering)).all()
    return [_to_summary(u) for u in users]


@router.post(
    "/users",
    response_model=AdminUserSummary,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account with a temporary password + forced first change (admin only).",
)
def create_user(
    body: UserCreate, request: Request, _admin: AdminDep, db: SessionDep
) -> AdminUserSummary:
    if db.scalar(select(User.id).where(User.username == body.username)) is not None:
        raise APIError(409, "username_taken", "that username is already in use")
    # The password is generated and mailed (10.B24), so it is sent **before** the account is
    # written: an account whose password nobody will ever read is not half a success, and this
    # ordering means a refusal leaves nothing behind to clean up.
    password = _mail_password(
        request,
        db,
        sysmsg.CREDENTIALS_CREATED.key,
        first_name=body.first_name,
        address=body.username,
        user_id=0,
    )
    user = User(
        username=body.username,
        first_name=body.first_name,
        last_name=body.last_name,
        password_hash=hash_password(password),
        role=body.role,
        is_active=True,
        must_change_password=True,  # USR-R2: forced change at first login
        # Announcements sent before this account existed are not its backlog (10.B12): the
        # pointer starts at the newest one, so a new inbox opens empty.
        last_broadcast_read_id=latest_broadcast_id(db),
    )
    db.add(user)
    db.commit()
    db.refresh(user)  # load server-side defaults (id, created_at)
    _enable_email(db, user.id)
    return _to_summary(user)


def _enable_email(db: SessionDep, user_id: int) -> None:
    """Email notifications on, for a brand-new account (10.B25).

    Written as a row rather than changed into a global default, because the two say different
    things: a default would also switch the channel back on for everybody who has deliberately
    turned it off. This is a fact recorded about *this* account at the moment it was created —
    and the reason it is on is that since 10.B23 the address is the username, so being reachable
    there is not an extra the person opted into, it is what the account is.
    """
    notif.set_user_enabled(db, user_id, EMAIL_PLUGIN_ID, True)


@router.post(
    "/users/{user_id}/reset-password",
    response_model=AdminUserSummary,
    summary="Generate a new password, mail it to the account, and force a change (admin only).",
)
def reset_password(
    user_id: int, request: Request, _admin: AdminDep, db: SessionDep
) -> AdminUserSummary:
    user = _target(db, user_id)
    # Mailed first, for the same reason as at creation: if it cannot be delivered, the account
    # keeps the password it has rather than one nobody can read (10.B24).
    password = _mail_password(
        request,
        db,
        sysmsg.CREDENTIALS_RESET.key,
        first_name=user.first_name,
        address=cred.address_of(user),
        user_id=user.id,
    )
    user.password_hash = hash_password(password)
    user.password_changed_at = datetime.now(tz=UTC)
    user.must_change_password = True  # USR-R2, as at creation
    # Every existing session dies with the old password: a reset exists precisely for the
    # case where somebody else may be holding it (AUTH-R5).
    user.token_version += 1
    user.refresh_jti = None
    db.commit()
    db.refresh(user)
    return _to_summary(user)


@router.delete(
    "/users/{user_id}",
    response_model=AdminUserSummary,
    summary="Mark an account for deletion after the grace period (admin only; never your own).",
)
def mark_for_deletion(
    user_id: int, request: Request, admin: AdminDep, db: SessionDep
) -> AdminUserSummary:
    """Soft delete (USR-R8): nothing is destroyed here, a date is set. The worker does the
    irreversible half when that date passes (10.B5)."""
    user = _target(db, user_id)
    _refuse_self(admin.sub, user)
    if user.deletion_marked_at is None:
        now = datetime.now(tz=UTC)
        grace = get_system_settings(db).user_deletion_retention_days
        user.deletion_marked_at = now
        # Computed once, here. The due date is a **fact about this marking**, not a formula
        # re-evaluated later: changing the grace period afterwards must not move the deadline
        # of an account already on its way out (10.B7).
        user.deletion_due_at = now + timedelta(days=grace)
        user.is_active = False
        user.token_version += 1
        user.refresh_jti = None
        db.commit()
        db.refresh(user)
        _courtesy(
            request,
            db,
            user,
            sysmsg.USER_MARKED_FOR_DELETION.key,
            deletion_due_date=user.deletion_due_at.date().isoformat(),
        )
    return _to_summary(user)


@router.post(
    "/users/{user_id}/restore",
    response_model=AdminUserSummary,
    summary="Cancel a pending deletion — the account comes back disabled, never active.",
)
def restore(user_id: int, _admin: AdminDep, db: SessionDep) -> AdminUserSummary:
    user = _target(db, user_id)
    if user.deletion_marked_at is None:
        raise APIError(409, "not_being_deleted", "this account is not marked for deletion")
    user.deletion_marked_at = None
    user.deletion_due_at = None
    # Deliberately **not** re-activated (USR-R10): undoing a deletion answers "do not destroy
    # this", which is a smaller statement than "let this person back in". Turning it on again
    # is a second, deliberate click.
    user.is_active = False
    db.commit()
    db.refresh(user)
    return _to_summary(user)


@router.patch(
    "/users/{user_id}",
    response_model=AdminUserSummary,
    summary="Enable or disable an account (admin only; never your own).",
)
def set_active(
    user_id: int, body: AdminUserPatch, request: Request, admin: AdminDep, db: SessionDep
) -> AdminUserSummary:
    user = _target(db, user_id)
    if not body.is_active:
        _refuse_self(admin.sub, user)
    if user.is_active != body.is_active:
        user.is_active = body.is_active
        # Kills the refresh family, so the session cannot be renewed and the account is out
        # **within the life of its access token** (AUTH-R5) — not instantly: nothing checks
        # `token_version` on an access token, by design, and a short-lived token is the price
        # of not hitting the database on every request. Re-enabling bumps it as well, so a
        # refresh minted before the disable can never come back to life afterwards.
        user.token_version += 1
        user.refresh_jti = None
        db.commit()
        db.refresh(user)
        if not body.is_active:
            _courtesy(request, db, user, sysmsg.USER_DISABLED.key)
    return _to_summary(user)
