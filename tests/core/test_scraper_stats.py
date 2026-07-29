"""Lifetime per-scraper statistics (9.B6c).

They exist because ``scrape_run`` has retention: aggregating that table answers "recently",
never "ever". The health counters are not a faster query at all — an anti-bot gate, a rate
limit and a ``robots.txt`` refusal are recorded nowhere else, which is exactly what was missing
during the July block, when the question was "since when, and how often".
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from src.core.scraper_stats import bump, get_stats, record_run


@pytest.fixture()
def session() -> Iterator[Session]:
    from src.core.db import create_schema, init_engine, new_session

    init_engine("sqlite+pysqlite:///:memory:")
    create_schema()
    s = new_session()
    try:
        yield s
    finally:
        s.close()


def test_the_row_is_created_on_first_use_and_declares_its_start(session: Session) -> None:
    """A cumulative counter with no start date misleads after a configuration change:
    politeness went from 1.5s to 11s in 0.8.1, and totals either side are not comparable."""
    row = get_stats(session, "dragon_store")
    assert row.since is not None
    assert row.runs_total == 0
    assert row.consecutive_failures == 0


def test_counters_accumulate_and_a_typo_is_refused(session: Session) -> None:
    bump(session, "dragon_store", {"gate_hits_total": 1, "http_requests_total": 4})
    bump(session, "dragon_store", {"gate_hits_total": 2})
    row = get_stats(session, "dragon_store")
    assert (row.gate_hits_total, row.http_requests_total) == (3, 4)

    # A misspelled counter has to fail loudly: silently it would be a number that never moves,
    # and nobody notices a statistic standing still for a month.
    with pytest.raises(ValueError, match="unknown scraper statistic"):
        bump(session, "dragon_store", {"gate_hitz": 1})


def test_a_failed_run_grows_the_streak_and_a_good_one_clears_it(session: Session) -> None:
    """The streak answers the question a monitoring page actually asks — "is it failing right
    now" — which a lifetime failure count cannot."""
    for _ in range(3):
        record_run(
            session,
            "dragon_store",
            ok=False,
            seconds=12.0,
            http_requests=2,
            cache_hits=0,
            bytes_downloaded=1000,
            politeness_wait_s=11.0,
            robots_denied=0,
            products_delivered=0,
        )
    row = get_stats(session, "dragon_store")
    assert (row.runs_total, row.runs_failed, row.consecutive_failures) == (3, 3, 3)
    assert row.last_failure_at is not None
    assert row.last_success_at is None

    record_run(
        session,
        "dragon_store",
        ok=True,
        seconds=20.0,
        http_requests=3,
        cache_hits=1,
        bytes_downloaded=2000,
        politeness_wait_s=22.0,
        robots_denied=0,
        products_delivered=38,
    )
    row = get_stats(session, "dragon_store")
    assert (row.runs_total, row.runs_ok, row.consecutive_failures) == (4, 1, 0)
    assert row.products_delivered_total == 38
    # Politeness waiting is kept apart from total run time on purpose: their ratio says whether
    # the bottleneck is us or the site's Crawl-delay.
    assert row.politeness_wait_s_total == 55
    assert row.run_seconds_total == 56


def test_statistics_are_per_scraper(session: Session) -> None:
    bump(session, "dragon_store", {"runs_total": 1})
    bump(session, "tp_scraper", {"runs_total": 5})
    assert get_stats(session, "dragon_store").runs_total == 1
    assert get_stats(session, "tp_scraper").runs_total == 5


def test_timestamps_are_named_explicitly(session: Session) -> None:
    with pytest.raises(ValueError, match="unknown scraper timestamp"):
        bump(session, "dragon_store", {}, stamp={"last_seen_at": datetime.now(UTC)})
