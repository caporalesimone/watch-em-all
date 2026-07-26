"""``robots.txt`` policy for the scraper HTTP client (CTX-R10).

Pure and dependency-free (stdlib only): this module **never** fetches. It turns a
already-retrieved ``robots.txt`` (status + body) into a :class:`RobotsPolicy` that
:class:`src.core.http.HttpClient` then enforces on the plugin's behalf — same
philosophy as politeness in CTX-R1: the plugin cannot bypass it even if it wanted to.

Two directives, two very different standings:

- ``Disallow``/``Allow`` are **standardised** (RFC 9309). Matching is delegated to
  :class:`urllib.robotparser.RobotFileParser`. Known divergence, kept on purpose: stdlib
  predates the RFC and resolves an ``Allow``/``Disallow`` overlap by **file order** (first
  match wins) rather than by the RFC's longest-match rule, so an ``Allow`` written *after*
  the ``Disallow`` it should override is ignored. Where the two differ we come out
  **stricter** than the standard, which is the safe direction: we skip a page we were
  allowed to fetch instead of fetching a forbidden one. Worth revisiting only if a site we
  actually scrape publishes such an overlap.
- ``Crawl-delay`` is **not** in RFC 9309 (which covers only User-agent/Allow/Disallow
  and the Sitemap reference). It is a de-facto extension: honoured by Bing and Yandex,
  explicitly ignored by Google. We honour it — a site publishing it is stating the rate
  it wants, and obeying costs us nothing. It is parsed here rather than via
  ``RobotFileParser.crawl_delay()`` because that one accepts integers only and silently
  drops fractional values.

Unreachability is decided per RFC 9309 §2.3.1: a ``4xx`` means "no policy published" and
everything is allowed; a ``5xx`` (or a network failure) means we must assume the whole
site is **disallowed** rather than guess.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

ROBOTS_PATH = "/robots.txt"
_DIRECTIVE_RE = re.compile(r"^([A-Za-z-]+)\s*:\s*(.*)$")


def origin_of(url: str) -> str:
    """``https://Www.Site.IT/a/b?q=1`` -> ``https://www.site.it`` (the robots scope)."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), "", "", ""))


def robots_url(origin: str) -> str:
    return origin.rstrip("/") + ROBOTS_PATH


def _ua_token(user_agent: str) -> str:
    """The product token a ``User-agent:`` line is matched against: everything before
    the first ``/`` (``"watch-em-all/0.8 (+url)"`` -> ``"watch-em-all"``)."""
    return user_agent.split("/")[0].strip().lower()


def _strip_comment(value: str) -> str:
    return value.split("#", 1)[0].strip()


def _groups(text: str) -> list[tuple[list[str], dict[str, str]]]:
    """Split a ``robots.txt`` into ``(agents, directives)`` groups. Consecutive
    ``User-agent:`` lines share one group of directives (the usual convention)."""
    groups: list[tuple[list[str], dict[str, str]]] = []
    agents: list[str] = []
    directives: dict[str, str] = {}
    prev_was_agent = False

    for raw in text.splitlines():
        match = _DIRECTIVE_RE.match(raw.strip())
        if match is None:
            continue
        name, value = match.group(1).lower(), _strip_comment(match.group(2))
        if name == "user-agent":
            if not prev_was_agent:  # a directive line closed the previous group
                if agents:
                    groups.append((agents, directives))
                agents, directives = [], {}
            agents.append(value.lower())
            prev_was_agent = True
            continue
        prev_was_agent = False
        directives.setdefault(name, value)

    if agents:
        groups.append((agents, directives))
    return groups


def parse_crawl_delay(text: str, user_agent: str) -> float | None:
    """The ``Crawl-delay`` that applies to ``user_agent``: a group naming us wins over
    the catch-all ``*`` group. ``None`` when the site declares none (or an unparseable
    one). Fractional values are supported."""
    token = _ua_token(user_agent)
    specific: float | None = None
    wildcard: float | None = None

    for agents, directives in _groups(text):
        raw = directives.get("crawl-delay")
        if raw is None:
            continue
        try:
            delay = float(raw)
        except ValueError:
            continue
        if delay < 0:
            continue
        for agent in agents:
            if agent == "*":
                wildcard = delay if wildcard is None else wildcard
            elif agent and agent in token:
                specific = delay if specific is None else specific

    return specific if specific is not None else wildcard


def count_disallow_rules(text: str) -> int:
    """Non-empty ``Disallow:`` lines in the whole file — for the log line only, so a
    reader can tell "no restrictions published" from "12 paths are off-limits"."""
    count = 0
    for raw in text.splitlines():
        match = _DIRECTIVE_RE.match(raw.strip())
        if match is None:
            continue
        if match.group(1).lower() == "disallow" and _strip_comment(match.group(2)):
            count += 1
    return count


@dataclass(frozen=True)
class RobotsPolicy:
    """What a site's ``robots.txt`` permits us, plus the rate it asks for."""

    origin: str
    user_agent: str
    crawl_delay: float | None = None
    # False only when robots.txt could not be retrieved (5xx / network): RFC 9309 then
    # requires assuming the whole site is off-limits.
    reachable: bool = True
    # True when no policy applies (4xx: nothing published) — everything is allowed.
    allow_all: bool = False
    rules: RobotFileParser | None = None
    disallow_rules: int = 0

    def allows(self, url: str) -> bool:
        if not self.reachable:
            return False
        if self.allow_all or self.rules is None:
            return True
        return self.rules.can_fetch(self.user_agent, url)

    def interval_floor(self, configured_s: float) -> float:
        """The delay to actually use: never faster than either what the admin configured
        or what the site asked for."""
        return max(configured_s, self.crawl_delay or 0.0)


def policy_from_response(
    origin: str, user_agent: str, *, status_code: int, body: bytes
) -> RobotsPolicy:
    """Build the policy from a retrieved ``robots.txt`` (RFC 9309 §2.3.1 status rules)."""
    if status_code >= 500:
        return RobotsPolicy(origin=origin, user_agent=user_agent, reachable=False)
    if status_code >= 400:
        return RobotsPolicy(origin=origin, user_agent=user_agent, allow_all=True)

    text = body.decode("utf-8", errors="replace")
    rules = RobotFileParser()
    rules.set_url(robots_url(origin))
    rules.parse(text.splitlines())
    rules.modified()  # arm can_fetch: it refuses everything while last_checked is unset
    return RobotsPolicy(
        origin=origin,
        user_agent=user_agent,
        crawl_delay=parse_crawl_delay(text, user_agent),
        rules=rules,
        disallow_rules=count_disallow_rules(text),
    )


def unreachable_policy(origin: str, user_agent: str) -> RobotsPolicy:
    """``robots.txt`` could not be fetched at all (timeout / DNS / connection refused):
    same standing as a 5xx — assume the whole site is disallowed."""
    return RobotsPolicy(origin=origin, user_agent=user_agent, reachable=False)
