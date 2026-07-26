"""Tests for the pure ``robots.txt`` policy module (``src/core/robots.py``, CTX-R10).

No HTTP here: the module never fetches. It is handed a status + body and must decide what
we are allowed to do — including the two failure modes of RFC 9309 §2.3.1, which are easy
to get backwards (a missing file is permissive, an unreachable one is not).
"""

from __future__ import annotations

from src.core.robots import (
    count_disallow_rules,
    origin_of,
    parse_crawl_delay,
    policy_from_response,
    robots_url,
    unreachable_policy,
)

UA = "watch-em-all/0.8 (+https://github.com/caporalesimone/watch-em-all)"

# What Dragon Store actually publishes (checked 2026-07-26).
DRAGON_STORE = b"User-agent: *\nCrawl-delay: 10\n"


def test_origin_and_robots_url_normalise_the_host() -> None:
    assert origin_of("https://WWW.Site.IT/a/b?q=1#frag") == "https://www.site.it"
    assert robots_url("https://www.site.it") == "https://www.site.it/robots.txt"


def test_dragon_store_policy_allows_everything_at_ten_seconds() -> None:
    """The real file: no Disallow at all, one Crawl-delay. Crawling is permitted; the only
    condition is the rate — which is precisely the condition we had been breaking."""
    policy = policy_from_response(
        "https://www.dragonstore.it", UA, status_code=200, body=DRAGON_STORE
    )
    assert policy.crawl_delay == 10.0
    assert policy.disallow_rules == 0
    assert policy.allows("https://www.dragonstore.it/x.1.19.192.gp.25879.uw")


def test_crawl_delay_is_a_floor_never_a_ceiling() -> None:
    policy = policy_from_response(
        "https://www.dragonstore.it", UA, status_code=200, body=DRAGON_STORE
    )
    assert policy.interval_floor(11.0) == 11.0  # our slower value stands
    assert policy.interval_floor(1.5) == 10.0  # the site's slower value wins


def test_no_crawl_delay_leaves_the_configured_interval_alone() -> None:
    policy = policy_from_response("https://s.it", UA, status_code=200, body=b"User-agent: *\n")
    assert policy.crawl_delay is None
    assert policy.interval_floor(11.0) == 11.0


def test_disallow_is_enforced_and_counted() -> None:
    body = b"User-agent: *\nDisallow: /cart\nDisallow: /admin\n"
    policy = policy_from_response("https://s.it", UA, status_code=200, body=body)
    assert policy.disallow_rules == 2
    assert not policy.allows("https://s.it/cart/mine")
    assert not policy.allows("https://s.it/admin")
    assert policy.allows("https://s.it/products/1")


def test_allow_wins_when_it_precedes_the_disallow() -> None:
    """``urllib.robotparser`` resolves overlaps by **file order**, not by the longest-match
    rule RFC 9309 specifies. So an ``Allow`` placed first is honoured..."""
    body = b"User-agent: *\nAllow: /cart/public\nDisallow: /cart\n"
    policy = policy_from_response("https://s.it", UA, status_code=200, body=body)
    assert policy.allows("https://s.it/cart/public")
    assert not policy.allows("https://s.it/cart/mine")


def test_a_later_allow_does_not_override_an_earlier_disallow() -> None:
    """...and one placed last is not. We keep stdlib's behaviour deliberately: where the two
    differ we end up *stricter* than the RFC, which is the safe direction to be wrong in —
    we skip a page we were in fact allowed to fetch, rather than fetching a forbidden one."""
    body = b"User-agent: *\nDisallow: /cart\nAllow: /cart/public\n"
    policy = policy_from_response("https://s.it", UA, status_code=200, body=body)
    assert not policy.allows("https://s.it/cart/public")


def test_a_group_naming_us_beats_the_wildcard() -> None:
    body = b"User-agent: *\nCrawl-delay: 30\n\nUser-agent: watch-em-all\nCrawl-delay: 5\n"
    assert parse_crawl_delay(body.decode(), UA) == 5.0
    # Someone else's group must not apply to us.
    assert parse_crawl_delay(body.decode(), "other-bot/1.0") == 30.0


def test_consecutive_user_agent_lines_share_one_group() -> None:
    body = "User-agent: bingbot\nUser-agent: watch-em-all\nCrawl-delay: 7\n"
    assert parse_crawl_delay(body, UA) == 7.0


def test_fractional_and_malformed_crawl_delays() -> None:
    # urllib.robotparser drops fractional values (int only) — we keep them.
    assert parse_crawl_delay("User-agent: *\nCrawl-delay: 0.5\n", UA) == 0.5
    assert parse_crawl_delay("User-agent: *\nCrawl-delay: soon\n", UA) is None
    assert parse_crawl_delay("User-agent: *\nCrawl-delay: -5\n", UA) is None
    assert parse_crawl_delay("User-agent: *\nCrawl-delay: 10 # be nice\n", UA) == 10.0


def test_missing_robots_allows_everything() -> None:
    """RFC 9309 §2.3.1: 4xx means no policy is published, not that we are forbidden."""
    policy = policy_from_response("https://s.it", UA, status_code=404, body=b"nope")
    assert policy.allow_all
    assert policy.reachable
    assert policy.allows("https://s.it/anything")


def test_unreachable_robots_disallows_the_whole_origin() -> None:
    """The mirror-image rule: a 5xx (or no answer at all) means assume off-limits."""
    for policy in (
        policy_from_response("https://s.it", UA, status_code=503, body=b"busy"),
        unreachable_policy("https://s.it", UA),
    ):
        assert not policy.reachable
        assert not policy.allows("https://s.it/anything")


def test_count_disallow_rules_ignores_the_empty_allow_all_form() -> None:
    # "Disallow:" with nothing after it is the idiom for "allow everything".
    assert count_disallow_rules("User-agent: *\nDisallow:\n") == 0
    assert count_disallow_rules("User-agent: *\nDisallow: /x\n") == 1
