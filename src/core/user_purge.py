"""The irreversible half of deleting an account (10.B5, USR-R9/R10).

10.B3 only marks: it writes a deadline and switches the account off. This is what happens
when that deadline passes — once a day from the worker, or the moment an administrator says
so (10.B27), which is the same destruction with a different trigger and therefore the same
function.

The order matters and is the whole design. **Plugins first, core last**: a plugin owns
tables the core knows nothing about, so if the core row went first those rows would be
orphaned with no way left to find them. And the core cascade only runs **if every plugin
succeeded** — a partial deletion is the one outcome nobody can recover from, because the
account that could still be found is gone while some of its data is not. A plugin that
raises leaves the user marked, logs the reason, and the next day tries again.

**The farewell mail comes last**, after the delete has committed (10.B26). Told beforehand it
could be a lie — a plugin may refuse and the account survive — so the name and the address are
read while the row still exists and the message goes out once there is genuinely nothing left.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core import direct_mail, system_messages
from src.core.models import User
from src.core.notify import mail_account_notice
from src.core.plugins.context import build_context
from src.core.plugins.registry import LoadedPlugin

if TYPE_CHECKING:
    from src.core.plugins.base import NotifierPlugin

log = logging.getLogger("wea.worker.user_purge")


def due_users(session: Session, now: datetime) -> list[User]:
    """Accounts whose grace period has run out. Marked *and* due: an account marked
    yesterday with a 30-day grace is not this job's business."""
    return list(
        session.scalars(
            select(User)
            .where(User.deletion_marked_at.is_not(None), User.deletion_due_at <= now)
            .order_by(User.id)
        )
    )


def purge_due_users(
    session: Session,
    now: datetime,
    plugins: list[LoadedPlugin],
    notifiers: list[NotifierPlugin] | None = None,
) -> int:
    """Destroy every account past its deadline. Returns how many were actually removed.

    Never raises: this runs inside the worker's daily maintenance, and one stuck account
    must not stop the others or the loop.
    """
    removed = 0
    for user in due_users(session, now):
        if purge_user(session, user, plugins, notifiers or [], reason="grace period expired"):
            removed += 1
    return removed


def purge_user(
    session: Session,
    user: User,
    plugins: list[LoadedPlugin],
    notifiers: list[NotifierPlugin],
    *,
    reason: str,
) -> bool:
    """Destroy one account for good. ``True`` when it is actually gone.

    Shared by the nightly sweep and the administrator's *delete permanently* (10.B27): what
    "delete" means must not depend on who asked, or the immediate path would quietly grow a
    second answer to "and what about the plugins' data".
    """
    # Read while there is still a row to read them from: the farewell mail is sent afterwards.
    user_id, username = user.id, user.username
    first_name, address, locale = user.first_name, direct_mail.address_of(user), user.locale

    if not _purge_plugin_data(user_id, username, plugins):
        return False  # stays marked, with the reason in the log; retried tomorrow
    # Core cascade: products, carts, alerts and the rest go with the row (their foreign
    # keys declare ON DELETE CASCADE). `price_history` is untouched by design — it keys
    # on product identity, not on the person who was watching.
    session.delete(user)
    session.commit()
    log.info("account purged: %s (id=%s), %s", username, user_id, reason)

    try:
        mail_account_notice(
            session,
            notifiers,
            system_messages.USER_DELETED.key,
            user_id=user_id,
            first_name=first_name,
            username=username,
            address=address,
            locale=locale,
        )
    except Exception:  # the account is already gone; a mail failure has nothing left to undo
        log.warning("could not tell %s that the account was deleted", address, exc_info=True)
    return True


def _purge_plugin_data(user_id: int, username: str, plugins: list[LoadedPlugin]) -> bool:
    """Every plugin's turn, in sequence. False as soon as one fails."""
    for lp in plugins:
        context = build_context(lp.manifest, lp.plugin)
        try:
            lp.plugin.delete_user_data(context, user_id)
        except Exception:
            log.exception(
                "purge of %s (id=%s) aborted: plugin %s could not delete its data; "
                "the account stays marked and will be retried",
                username,
                user_id,
                lp.plugin.plugin_id,
            )
            return False
        finally:
            context.db.close()
    return True
