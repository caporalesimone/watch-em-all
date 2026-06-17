"""Initial-admin bootstrap (AUTH-R8, 1.B3).

First boot with no users: create the admin from the environment, with a forced
password change. Idempotent — does nothing once any user exists.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.models import User
from src.core.security import hash_password

log = logging.getLogger(__name__)


def ensure_initial_admin(
    session: Session, *, username: str, password: str | None, locale: str
) -> None:
    if session.scalar(select(User.id).limit(1)) is not None:
        return
    if not password:
        log.warning("no users yet and ADMIN_INITIAL_PASSWORD is unset; skipping admin bootstrap")
        return
    session.add(
        User(
            username=username,
            # The bootstrap admin starts with a first name only; the surname is
            # completed later. Admin-created users require both filled (USR).
            first_name="Admin",
            last_name="",
            password_hash=hash_password(password),
            role="admin",
            is_active=True,
            locale=locale,
            must_change_password=True,
        )
    )
    session.commit()
    log.info("created initial admin %r (password change forced at first login)", username)
