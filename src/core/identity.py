"""What an account is called (10.B23): the username **is** an email address.

Since phase 10 an account is created by an administrator who types an address, and that address
is both the login name and where the system writes to that person. One field instead of two, so
there is never a pair that can disagree about where somebody's mail goes.

Two rules, and they are the whole module:

- **it must look like an address** — validated here, on the server, which is the last line of
  defence (the page validates too, but a page can be bypassed with one ``curl``);
- **it is stored lowercase and compared lowercase** — an address is case-insensitive in
  practice, and normalising *on write* keeps the comparison an ordinary equality on a unique,
  indexed column instead of a ``lower()`` the database cannot use an index for.

**One account is exempt**, and only one: the bootstrap admin, which exists before anybody can
type anything (``WEA_ADMIN_INITIAL_USERNAME``, normally ``admin``). The exemption sustains
itself — every *other* account is created through an API that requires an address — and it is
also how the rest of the system recognises that account: it is the only one whose username is
not an address, which is why it is the only one that needs a separate ``contact_email``.
"""

from __future__ import annotations

import re

USERNAME_MAX = 254
"""RFC 5321 caps a forward-path at 254 characters; the column is sized to match (10.X2)."""

# Deliberately not an RFC 5322 parser. That grammar admits quoted local parts, comments and
# domain literals — things no one types into a login form and every downstream tool then
# mishandles. This accepts the shape people actually use and refuses the rest: one `@`, a local
# part without spaces or stray dots, and a domain with at least one dot and a real label after it.
_LOCAL = r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*"
_LABEL = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
_EMAIL_RE = re.compile(rf"^{_LOCAL}@{_LABEL}(?:\.{_LABEL})+$")


def normalize_username(raw: str) -> str:
    """The stored form: trimmed and lowercased.

    Applied on every write — creation, and the bootstrap admin too — so that reads can compare
    with a plain ``==``. Casing a person types is theirs; casing the database keeps is ours.
    """
    return raw.strip().lower()


def is_email(value: str) -> bool:
    """Whether ``value`` has the shape of an email address.

    Also the test for *"is this the bootstrap admin"*: that account is the only one whose
    username is not an address.
    """
    value = value.strip()
    return len(value) <= USERNAME_MAX and _EMAIL_RE.match(value) is not None
