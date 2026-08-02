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
"""

from __future__ import annotations

import nh3
from markdown_it import MarkdownIt

# CommonMark, minus raw HTML: `html=False` makes the parser escape it rather than forward
# it. Kept module-level — building the parser costs more than rendering a short message.
_MD = MarkdownIt("commonmark", {"html": False, "linkify": False})

# What a notification may contain. Deliberately short: this is a message to a person, not a
# page. No images (a remote image in an email is a tracking pixel by another name, and phase
# 7 already decided email carries links only), no tables, no headings above the body's own
# level — a message that renders an <h1> inside somebody's history looks like the app broke.
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
