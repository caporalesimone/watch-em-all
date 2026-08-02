"""The catalog of texts the system writes to people (ADMSG-R7..R10, 10.B16).

Everything the core says to a user in words lives here: the three account-lifecycle notices —
disabled, scheduled for deletion, deleted (USR-R11, 10.B26) — and the two credential mails
(10.B24). One catalog, because the alternative is what phase 10 found when it opened: the same
sentence written at the call site that needed it, free to drift from the one next to it.

Four properties, each of them a rule from the spec rather than a convenience:

- **The catalog is code, the overrides are data** (ADMSG-R9). Keys, default texts and declared
  placeholders are the constants below; the database holds only what an admin has rewritten. Add
  a message to the core and it appears in the admin list with no migration and nothing to seed.
- **Resolution happens once, in :func:`resolve`** (ADMSG-R10), and always in the same order:
  override or default → the translation point (V1: identity) → placeholder substitution. No
  caller formats anything itself.
- **An unknown placeholder is text, never an exception** (ADMSG-R8). An admin who writes
  ``{usernme}`` gets those nine characters delivered, not a 500 at the moment somebody's account
  is disabled. The editor warns; the runtime does not punish.
- **Some placeholders are required.** Only the credential mails declare any, and only one:
  ``{password}``. It is the single message whose breakage locks a person out, so it is the
  single one that refuses an override without it (Simone's decision, 2026-08-02).
"""

from __future__ import annotations

import string
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.models import SystemMessageTemplate


@dataclass(frozen=True)
class SystemMessage:
    """One catalog entry: a stable key, the core's default text, and what may go inside it."""

    key: str
    title: str
    body: str
    placeholders: tuple[str, ...]
    required: tuple[str, ...] = field(default=())


# The three account-lifecycle notices open the same way on purpose: *Your Watch 'Em All account
# (**{username}**) has …*. They are the only messages a person may receive without having asked
# for anything, quite possibly at an address that carries more than one account, so each of them
# names which account it is about — in bold, because that is the word the reader is looking for.
USER_DISABLED = SystemMessage(
    key="user.disabled",
    title="Your Watch 'Em All account has been disabled",
    body=(
        "Hello {first_name},\n\n"
        "Your Watch 'Em All account (**{username}**) has been disabled by an administrator, so "
        "you can no longer sign in. Nothing of yours has been removed.\n\n"
        "If you think this is a mistake, get in touch with whoever administers the "
        "installation."
    ),
    placeholders=("first_name", "username"),
)

USER_MARKED_FOR_DELETION = SystemMessage(
    key="user.marked_for_deletion",
    title="Your Watch 'Em All account is scheduled for deletion",
    body=(
        "Hello {first_name},\n\n"
        "Your Watch 'Em All account (**{username}**) has been added to the list of accounts due "
        "to be removed, and is scheduled for deletion on **{deletion_due_date}**. You can no "
        "longer sign in, but until that date nothing is destroyed and an administrator can "
        "still bring the account back.\n\n"
        "If this is not what you expected, get in touch with whoever administers the "
        "installation before that date."
    ),
    placeholders=("first_name", "username", "deletion_due_date"),
)

USER_DELETED = SystemMessage(
    key="user.deleted",
    title="Your Watch 'Em All account has been deleted",
    body=(
        "Hello {first_name},\n\n"
        "Your Watch 'Em All account (**{username}**) has been permanently deleted, together with "
        "everything it held: watches, carts, alerts and notification history.\n\n"
        "This cannot be undone and there is nothing left to restore. If you need access again, "
        "an administrator has to create a new account for you."
    ),
    placeholders=("first_name", "username"),
)

CREDENTIALS_CREATED = SystemMessage(
    key="user.credentials.created",
    title="Your Watch 'Em All account",
    body=(
        "Hello {first_name},\n\n"
        "An account has been created for you on Watch 'Em All.\n\n"
        "- **Username:** {username}\n"
        "- **Password:** {password}\n\n"
        "You will be asked to choose your own password the first time you sign in."
    ),
    placeholders=("first_name", "username", "password"),
    required=("password",),
)

CREDENTIALS_RESET = SystemMessage(
    key="user.credentials.reset",
    title="Your Watch 'Em All password has been reset",
    body=(
        "Hello {first_name},\n\n"
        "An administrator has reset the password of your Watch 'Em All account.\n\n"
        "- **Username:** {username}\n"
        "- **Password:** {password}\n\n"
        "The previous password no longer works and any session left open has been signed out. "
        "You will be asked to choose your own password when you sign in."
    ),
    placeholders=("first_name", "username", "password"),
    required=("password",),
)

CATALOG: dict[str, SystemMessage] = {
    m.key: m
    for m in (
        USER_DISABLED,
        USER_MARKED_FOR_DELETION,
        USER_DELETED,
        CREDENTIALS_CREATED,
        CREDENTIALS_RESET,
    )
}


class UnknownMessageKey(KeyError):
    """A key that is not in the catalog. Always a programming error, never user input."""


def entry(key: str) -> SystemMessage:
    try:
        return CATALOG[key]
    except KeyError as exc:
        raise UnknownMessageKey(key) from exc


# --------------------------------------------------------------------------- rendering


class _Literal(dict[str, object]):
    """A mapping that answers an unknown key with the key itself, braces included.

    This is ADMSG-R8 in three lines: an override written with a placeholder the catalog does not
    declare renders as the literal text the admin typed. The alternative — letting ``format``
    raise — would turn a typo in a settings page into a failure at the moment the system needs
    to tell somebody their account is going away.
    """

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _fill(text: str, values: dict[str, object]) -> str:
    return string.Formatter().vformat(text, (), _Literal(values))


def translate(text: str, locale: str) -> str:
    """The translation point (ADMSG-R10). V1 is English-only, so this is the identity — it
    exists as a named step because the *order* matters: translate first, substitute after, or a
    value containing braces would be reinterpreted by the next stage."""
    _ = locale
    return text


def placeholders_in(text: str) -> set[str]:
    """Every ``{name}`` the text uses. Used by the editor to warn (ADMSG-R8) and by the
    override validation to insist on the required ones."""
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def override(db: Session, key: str) -> SystemMessageTemplate | None:
    return db.get(SystemMessageTemplate, key)


def current(db: Session, key: str) -> tuple[str, str]:
    """The text in force for this key — the override if there is one, the default otherwise.
    Unrendered: no translation, no placeholders filled. For the admin editor."""
    row = override(db, key)
    if row is not None:
        return row.title, row.body
    default = entry(key)
    return default.title, default.body


def resolve(db: Session, key: str, *, locale: str = "en", **values: object) -> tuple[str, str]:
    """The one resolution path (ADMSG-R10): override or default → translate → fill.

    Returns ``(title, body)`` ready to be written to history and handed to the channels. Every
    call site goes through here, so a message cannot come out formatted one way in the mail and
    another way in the app.
    """
    title, body = current(db, key)
    return (
        _fill(translate(title, locale), values),
        _fill(translate(body, locale), values),
    )


def validate_override(key: str, title: str, body: str) -> tuple[list[str], list[str]]:
    """Check an override before it is saved. Returns ``(unknown, missing_required)``.

    The two are not the same kind of problem and the caller treats them differently: an
    **unknown** placeholder is a warning — it will be delivered as literal text, which is
    untidy but harmless — while a **missing required** one is a refusal, because the only
    placeholders in that list are the ones whose absence makes the message useless.
    """
    declared = set(entry(key).placeholders)
    used = placeholders_in(title) | placeholders_in(body)
    unknown = sorted(used - declared)
    missing = [name for name in entry(key).required if name not in used]
    return unknown, missing


def all_keys(db: Session) -> list[str]:
    """Every catalog key, in a stable order, whether or not it carries an override."""
    _ = db
    return list(CATALOG)


def overridden_keys(db: Session) -> set[str]:
    return set(db.scalars(select(SystemMessageTemplate.key)).all())
