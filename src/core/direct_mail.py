"""Mail that must not travel through the notification pipeline (10.B24, 10.B26).

Anything the system says to somebody normally becomes an ``alert_log`` row and is then delivered
by whichever channels that person has active. Two kinds of message cannot work that way, for two
different reasons, and both live here.

- **Credentials** (10.B24). A generated password written to ``alert_log`` would sit in clear in
  the in-app history, readable by anybody who can open that page. So it is written nowhere: the
  email plugin, the system SMTP config, one message, no row.
- **Account-lifecycle notices** (10.B26). *Disabled*, *scheduled for deletion*, *deleted* is
  exactly the news somebody cannot come and read in the app, because the account it is about is
  the one they can no longer sign into — and the last of the three is sent when there is no row
  left to hang a delivery off.

Both consequently **ignore the user's email preference**. That switch governs notifications:
what a person asked to be told about. None of these is one in that sense — they are the system
saying what has happened *to their account*, and turning off price alerts is not consent to
being locked out in silence.

The texts live in the system-message catalog (:mod:`src.core.system_messages`) like everything
else the core says in words, so an administrator rewrites them in one place. The credential
mails carry ``{password}`` among their *required* placeholders: an override that would send a
credential without the credential in it is refused when it is saved, and checked again here —
this is the one message whose breakage locks a person out.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from src.core import notifiers as notif
from src.core import system_messages as sysmsg
from src.core.alert_engine import TextMessageEvent
from src.core.contracts import ACCOUNT_EMAIL_KEY, NotificationKind
from src.core.models import User

if TYPE_CHECKING:
    from datetime import datetime

    from src.core.plugins.base import NotifierPlugin


class DirectMailError(Exception):
    """The message could not be put in front of the person it is about. Never raised for a
    wording problem — only for a channel that is off, unconfigured, or that refused it."""


def email_channel(notifiers: list[NotifierPlugin]) -> NotifierPlugin | None:
    for plugin in notifiers:
        if plugin.plugin_id == notif.EMAIL_PLUGIN_ID:
            return plugin
    return None


def channel_ready(db: Session, plugin: NotifierPlugin | None) -> bool:
    """Whether anything can actually be delivered right now: the plugin is loaded, the admin
    kill-switch is on, and the system SMTP config is complete. Checked **before** anything is
    written, so a refusal leaves nothing behind."""
    if plugin is None:
        return False
    if not notif.admin_enabled(db, plugin.plugin_id):
        return False
    return notif.is_complete(
        plugin.get_admin_config_schema(), notif.admin_config(db, plugin.plugin_id)
    )


def render(
    db: Session, key: str, *, first_name: str, username: str, locale: str = "en", **values: object
) -> tuple[str, str]:
    return sysmsg.resolve(
        db, key, locale=locale, first_name=first_name or username, username=username, **values
    )


def send(
    db: Session,
    plugin: NotifierPlugin | None,
    *,
    key: str,
    user_id: int,
    first_name: str,
    username: str,
    address: str,
    now: datetime,
    locale: str = "en",
    **values: object,
) -> None:
    """Deliver one catalog message straight to an address. Raises :class:`DirectMailError`.

    ``username`` and ``address`` are two different things and are asked for separately: the
    first is what this person types to sign in, the second is where the mail goes. They are the
    same string for every account but the bootstrap admin — which is precisely the one that
    would otherwise be told its username is an address it never signs in with.
    """
    title, body = render(db, key, first_name=first_name, username=username, locale=locale, **values)
    _deliver(
        db, plugin, user_id=user_id, address=address, now=now, title=title, body=body, locale=locale
    )


def send_password(
    db: Session,
    plugin: NotifierPlugin | None,
    *,
    key: str,
    user_id: int,
    first_name: str,
    username: str,
    address: str,
    password: str,
    now: datetime,
) -> None:
    """The same send, with the one guarantee a credential mail has to carry.

    ``user_id`` travels in the event only because the notifier contract carries one; nothing is
    looked up by it and nothing is written against it. The config handed to the plugin is the
    **system** config plus the destination — the user's own row is not consulted, which is how
    the send stays independent of whether that person wants email notifications.
    """
    title, body = render(db, key, first_name=first_name, username=username, password=password)
    # A last look before it goes out. The save-time validation already refuses an override
    # without `{password}`, but a row could have been written before that rule existed, or by
    # hand — and this is the message where an empty promise is not a cosmetic mistake.
    if password not in body:
        raise DirectMailError(f"{key}: the rendered text does not carry the password")
    _deliver(db, plugin, user_id=user_id, address=address, now=now, title=title, body=body)


def _deliver(
    db: Session,
    plugin: NotifierPlugin | None,
    *,
    user_id: int,
    address: str,
    now: datetime,
    title: str,
    body: str,
    locale: str = "en",
) -> None:
    if plugin is None:
        raise DirectMailError("the email channel is not available")
    event = TextMessageEvent(
        kind=NotificationKind.SYSTEM_MESSAGE,
        user_id=user_id,
        generated_at=now,
        title=title,
        body=body,
    )
    config = {
        **notif.admin_config(db, plugin.plugin_id),
        ACCOUNT_EMAIL_KEY: address,
    }
    try:
        plugin.send(event, config, locale)
    except Exception as exc:  # NotifierDeliveryError, after the plugin's own retries
        raise DirectMailError(str(exc)) from exc


def address_of(user: User) -> str:
    """Where this account is reached: its own address, which for everybody but the bootstrap
    admin *is* the username (10.B23/10.B25)."""
    return user.contact_email or user.username
