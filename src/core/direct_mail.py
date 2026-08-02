"""Getting a password to the person it belongs to (10.B24).

Since 10.B23 an account is an email address, and since 10.B24 nobody chooses its first password:
the server generates one and mails it. This module is the whole of *"and mails it"*.

**It does not use the notification pipeline, and that is the point.** A digest or an admin
message is written to ``alert_log`` before any channel sees it — which is right for a
notification and wrong for a credential: the password would sit in clear in the in-app history,
readable by anybody who can open that page. So this is a direct send: the email plugin, the
system SMTP config, one message, no row anywhere. Two consequences follow from the same reason:

- it **ignores the user's email preference**. The switch governs notifications; a credential is
  not one. Somebody who turned email notifications off still has to be able to sign in.
- if the channel cannot deliver, the caller **refuses the whole operation**. An account created
  with a password nobody will ever read is not half a success, it is an account nobody can use.

The two texts it sends live in the system-message catalog
(:mod:`src.core.system_messages`) like every other thing the core says to somebody, with
``{password}`` among their *required* placeholders: an administrator may rewrite the wording,
and the validation refuses an override that would send a credential without the credential in
it. This is the one message whose breakage locks a person out, so it is the one that carries a
rule the others do not.
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


class CredentialMailError(Exception):
    """The password could not be put in front of its owner. Never raised for a wording problem —
    only for a channel that is off, unconfigured, or that refused the message."""


def email_channel(notifiers: list[NotifierPlugin]) -> NotifierPlugin | None:
    for plugin in notifiers:
        if plugin.plugin_id == notif.EMAIL_PLUGIN_ID:
            return plugin
    return None


def channel_ready(db: Session, plugin: NotifierPlugin | None) -> bool:
    """Whether a credential can actually be delivered right now: the plugin is loaded, the admin
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
    db: Session, key: str, *, first_name: str, username: str, password: str
) -> tuple[str, str]:
    title, body = sysmsg.resolve(
        db, key, first_name=first_name or username, username=username, password=password
    )
    # A last look before it goes out. The save-time validation already refuses an override
    # without `{password}`, but a row could have been written before that rule existed, or by
    # hand — and this is the message where an empty promise is not a cosmetic mistake.
    if password not in body:
        raise CredentialMailError(f"{key}: the rendered text does not carry the password")
    return title, body


def send_password(
    db: Session,
    plugin: NotifierPlugin | None,
    *,
    key: str,
    user_id: int,
    first_name: str,
    address: str,
    password: str,
    now: datetime,
) -> None:
    """Deliver one credential, directly. Raises :class:`CredentialMailError` on any failure.

    ``user_id`` travels in the event only because the notifier contract carries one; nothing is
    looked up by it and nothing is written against it. The config handed to the plugin is the
    **system** config plus the destination — the user's own row is not consulted, which is how
    the send stays independent of whether that person wants email notifications.
    """
    if plugin is None:
        raise CredentialMailError("the email channel is not available")
    title, body = render(db, key, first_name=first_name, username=address, password=password)
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
        plugin.send(event, config, "en")
    except Exception as exc:  # NotifierDeliveryError, after the plugin's own retries
        raise CredentialMailError(str(exc)) from exc


def address_of(user: User) -> str:
    """Where this account is reached: its own address, which for everybody but the bootstrap
    admin *is* the username (10.B23/10.B25)."""
    return user.contact_email or user.username
