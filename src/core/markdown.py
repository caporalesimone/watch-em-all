"""Markdown for message bodies (10.B14, AEV-R7 / CTX-R8).

Two functions, because a message has to reach two kinds of channel: one that can show
formatting (email, the in-app history) and one that cannot (anything plain-text). The same
source text goes to both, so the plain rendering is a *derivation* of the rich one rather
than a second thing to write — otherwise the two drift and a bullet list becomes a wall.

**Sanitised twice, on purpose.** The parser is told not to pass raw HTML through, and the
result is then run through `nh3` against a small allowlist. Belt and braces is warranted
here: the text is admin-authored, but "admin-authored" is a statement about who typed it,
not about what ends up in it — a pasted snippet is the ordinary way something hostile
arrives, and this output is rendered in everybody else's browser.

**Emoji need nothing.** They are ordinary characters and travel as such the whole way:
UTF-8 in the database, untouched by the parser and the sanitiser, and encoded per RFC 2047
by the stdlib when a mail subject carries one. There is no switch to turn on — the question
only comes up because headings used to be silently flattened in the same message.
"""

from __future__ import annotations

import nh3
from markdown_it import MarkdownIt

# CommonMark, minus raw HTML: `html=False` makes the parser escape it rather than forward
# it. Kept module-level — building the parser costs more than rendering a short message.
_MD = MarkdownIt("commonmark", {"html": False, "linkify": False})

# How far a heading is pushed down (10.B31). A message is rendered **inside** a page that
# already owns its <h1> and <h2>, so `#` at the top of a body is not the document's title —
# it is a section of somebody's notification. Shifting by two makes the markup say that, and
# it is why headings can be allowed at all: the original objection was that an <h1> in a
# notification card looks like the app broke, and it did.
_HEADING_SHIFT = 2


def _demote_headings(state: object) -> None:
    for token in getattr(state, "tokens", []):
        if token.type in ("heading_open", "heading_close"):
            level = int(token.tag[1:])
            token.tag = f"h{min(level + _HEADING_SHIFT, 6)}"


_MD.core.ruler.push("demote_headings", _demote_headings)

# What a notification may contain. Deliberately short: this is a message to a person, not a
# page. No images (a remote image in an email is a tracking pixel by another name, and phase
# 7 already decided email carries links only) and no tables. Headings **are** allowed since
# 10.B31, but only in the demoted range they come out in: h1 and h2 stay out of the list, so
# a body can never claim the page's own levels even if something else produced the HTML.
_ALLOWED_TAGS = {
    "p",
    "br",
    "strong",
    "em",
    "code",
    "pre",
    "blockquote",
    "ul",
    "ol",
    "li",
    "a",
    "h3",
    "h4",
    "h5",
    "h6",
}
_ALLOWED_ATTRS = {"a": {"href", "title"}}


def to_html(text: str) -> str:
    """Markdown → sanitised HTML, ready to drop into an email or a page.

    Links keep their href but are cleaned by `nh3`, which drops the schemes that are not
    http/https — a `javascript:` link is the one thing a message body could smuggle past a
    tag allowlist.
    """
    return nh3.clean(_MD.render(text), tags=_ALLOWED_TAGS, attributes=_ALLOWED_ATTRS)


def strip(text: str) -> str:
    """Markdown → plain text, for a channel that cannot show formatting.

    Rendered and *then* stripped rather than pattern-matched away: reusing the parser means
    the plain version can never disagree with the rich one about what the message says. The
    block structure survives as blank lines, which is what makes a stripped bullet list still
    readable as a list.
    """
    text_only = nh3.clean(_MD.render(text), tags=set(), attributes={})
    # `nh3` unescapes as it strips, so `&amp;` comes back as `&`; what is left is the run of
    # blank lines the block tags left behind.
    lines = [line.strip() for line in text_only.splitlines()]
    return "\n".join(line for line in lines if line)
