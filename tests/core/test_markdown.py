"""The Markdown helper the notifiers share (10.B14, CTX-R8/AEV-R7).

The interesting cases are not "does bold work" but the two that decide whether this is safe
and whether the plain fallback is worth having.
"""

from __future__ import annotations

from src.core.markdown import strip, to_html


def test_ordinary_formatting_survives() -> None:
    html = to_html("A **bold** word and a [link](https://example.com).")
    assert "<strong>bold</strong>" in html
    assert 'href="https://example.com"' in html


def test_headings_render_but_two_levels_down() -> None:
    """10.B31. They were dropped altogether because an ``<h1>`` inside a notification card
    looks like the app broke — which was true of the level, not of the feature. Demoting says
    what a heading in a message actually is: a section of somebody's message, inside a page
    that already owns its own h1 and h2."""
    html = to_html("# Top\n\n## Under\n\n###### Deepest")
    assert "<h3>Top</h3>" in html
    assert "<h4>Under</h4>" in html
    # Already at the bottom of the scale: shifting cannot invent an h8.
    assert "<h6>Deepest</h6>" in html
    assert "<h1" not in html and "<h2" not in html


def test_emoji_travel_untouched() -> None:
    """Nothing has to be switched on for them: they are ordinary characters, and the parser
    and the sanitiser both leave them alone. Written down as a test because the question was
    asked, and an answer in prose decays."""
    html = to_html("# Rilascio \U0001f680\n\nCiao \U0001f44b **ok** ❤️")
    assert "\U0001f680" in html and "\U0001f44b" in html and "❤️" in html
    assert "\U0001f680" in strip("# Rilascio \U0001f680")


def test_html_written_into_the_source_never_becomes_an_element() -> None:
    """Admin-authored is a statement about who typed it, not about what is in it.

    Note what "safe" means here: the markup is **escaped, not deleted**. The reader still
    sees the characters they typed, which is the honest outcome for a message body — it is
    the browser that must never be handed an element, and it is not.
    """
    html = to_html("Hello <script>alert(1)</script> and <img src=x onerror=alert(1)>")
    assert "<script" not in html and "<img" not in html
    assert "&lt;script&gt;" in html, "escaped through, rather than silently swallowed"


def test_a_javascript_link_never_becomes_a_link() -> None:
    """The one thing a body could try to smuggle past a tag allowlist.

    Caught a layer earlier than expected: markdown-it validates the scheme itself and
    refuses to build the anchor at all, so the text survives as text and `nh3` is never
    asked to strip an href. Two defences, and the first one is enough.
    """
    html = to_html("[click me](javascript:alert(1))")
    assert "<a" not in html, "no anchor is built at all"
    assert "click me" in html, "the words stay; only the link-ness goes"


def test_the_plain_rendering_keeps_the_words_and_the_shape() -> None:
    plain = strip("# Title\n\nA **bold** word.\n\n- first\n- second")
    assert "<" not in plain and "**" not in plain
    assert "Title" in plain and "bold word." in plain
    # A list read as one run-on line is why this is derived from the rendered HTML rather
    # than from a regex over the source.
    assert "first" in plain.splitlines() and "second" in plain.splitlines()


def test_the_two_renderings_agree_about_what_the_message_says() -> None:
    source = "Maintenance tonight at **7am**. See [the notes](https://example.com)."
    for fragment in ("Maintenance tonight at", "7am", "the notes"):
        assert fragment in strip(source)
        assert fragment in to_html(source)
