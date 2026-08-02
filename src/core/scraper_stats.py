"""Lifetime statistics per scraper (9.B6c; phase 10 decides how to show them, 10.B20/10.F15).

One cumulative row per ``plugin_id``. It exists because ``scrape_run`` has retention: querying
that table answers "recently", never "ever". Two groups of writer, on purpose:

- the **runner** records what it can see from outside — did the run happen, did it succeed, how
  many requests and bytes went out, how much of it was politeness waiting;
- the **plugin** records what only it knows: an anti-bot gate, a rate limit, a page that would
  not parse. Today those exist solely as log lines, which is exactly what was missing during
  the 25 July block, when the question was "since when, and how often".

Every write goes through :func:`bump`, so a counter nobody thought about cannot silently start
diverging between callers.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.models import ScraperStats

# Counters callers may bump. Explicit, so a typo is an error rather than a number that never
# moves — the failure mode of a statistic nobody reads for a month.
_COUNTERS = frozenset(
    {
        "runs_total",
        "runs_ok",
        "runs_failed",
        "runs_skipped_locked",
        "http_requests_total",
        "cache_hits_total",
        "bytes_downloaded_total",
        "politeness_wait_s_total",
        "run_seconds_total",
        "rate_limited_total",
        "gate_hits_total",
        "gate_cleared_total",
        "robots_denied_total",
        "products_delivered_total",
        "pages_fetched_total",
        "parse_failures_total",
    }
)
_TIMESTAMPS = frozenset({"last_run_at", "last_success_at", "last_failure_at"})


def get_stats(session: Session, plugin_id: str) -> ScraperStats:
    """This scraper's row, created on first use. ``since`` is stamped then: a cumulative
    counter with no start date misleads after a configuration change — politeness went from
    1.5s to 11s in 0.8.1, and totals either side of that are not comparable."""
    row = session.scalar(select(ScraperStats).where(ScraperStats.plugin_id == plugin_id))
    if row is None:
        row = ScraperStats(plugin_id=plugin_id, since=datetime.now(UTC))
        session.add(row)
        session.flush()
    return row


def bump(
    session: Session,
    plugin_id: str,
    deltas: Mapping[str, int],
    *,
    consecutive_failures: int | None = None,
    stamp: Mapping[str, datetime] | None = None,
) -> None:
    """Add to this scraper's counters. Commits, because callers reach it from error paths where
    their own unit of work may be about to be rolled back — a statistic lost because the thing
    it was measuring failed is a statistic that only ever describes success.

    ``consecutive_failures`` is set rather than added: it is a streak, and the question in front
    of a monitoring page is "is it failing right now", not "how many times ever".
    """
    unknown = set(deltas) - _COUNTERS
    if unknown:
        raise ValueError(f"unknown scraper statistic(s): {sorted(unknown)}")
    row = get_stats(session, plugin_id)
    for name, delta in deltas.items():
        setattr(row, name, getattr(row, name) + delta)
    if consecutive_failures is not None:
        row.consecutive_failures = consecutive_failures
    for name, when in (stamp or {}).items():
        if name not in _TIMESTAMPS:
            raise ValueError(f"unknown scraper timestamp: {name}")
        setattr(row, name, when)
    session.commit()


def record_run(
    session: Session,
    plugin_id: str,
    *,
    ok: bool,
    seconds: float,
    http_requests: int,
    cache_hits: int,
    bytes_downloaded: int,
    politeness_wait_s: float,
    robots_denied: int,
    products_delivered: int,
) -> None:
    """One finished run, from the runner's point of view."""
    now = datetime.now(UTC)
    previous = get_stats(session, plugin_id).consecutive_failures
    bump(
        session,
        plugin_id,
        {
            "runs_total": 1,
            "runs_ok": 1 if ok else 0,
            "runs_failed": 0 if ok else 1,
            "run_seconds_total": int(seconds),
            "http_requests_total": http_requests,
            "cache_hits_total": cache_hits,
            "bytes_downloaded_total": bytes_downloaded,
            "politeness_wait_s_total": int(politeness_wait_s),
            "robots_denied_total": robots_denied,
            "products_delivered_total": products_delivered,
        },
        consecutive_failures=0 if ok else previous + 1,
        stamp={"last_run_at": now, ("last_success_at" if ok else "last_failure_at"): now},
    )
