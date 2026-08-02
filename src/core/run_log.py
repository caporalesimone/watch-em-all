"""Recording a scrape run, wherever it was started from (10.B20).

Until phase 10 only the worker wrote ``scrape_run`` / ``scrape_user_log`` and the lifetime
counters. The web path — *Scrape now*, and adding a watch — called ``run_for_user`` directly and
recorded **nothing**, while the counters the plugin bumps from inside (gate hits, rate limits,
pages, parse failures) went up regardless. The result was two numbers describing the same
traffic and disagreeing: ``http_requests_total`` counting only scheduled work, ``pages_fetched_
total`` counting all of it. An exposed counter is a counter somebody trusts.

So the recording lives here, once, and both callers use it:

- :func:`open_run` starts a run row and says how it was triggered — ``scheduled`` or ``manual``;
- :func:`run_one_user` is one person's slice of it: the log row, the before/after HTTP counters,
  the outcome;
- :func:`close_run` settles the status and folds the run into the lifetime statistics.

The worker keeps its own loop around these — the deadline, the per-user cooldown stamp and the
"one failure does not stop the others" rule are scheduling concerns, and the web path has none
of them. What is shared is the *arithmetic*, which is the part that was drifting.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy.orm import Session

from src.core.contracts import DeltaCounters
from src.core.models import ScrapeRun, ScrapeUserLog
from src.core.scraper_stats import bump, record_run

log = logging.getLogger(__name__)

HttpCounters = tuple[int, int]
"""``(request_count, cache_hits)`` read off the plugin context's HTTP client."""


class HttpTraffic(Protocol):
    """The counters :func:`record_traffic` reads. A structural type rather than an import of
    ``HttpClient``: this module records numbers, it has no business knowing how they are made.

    Read-only properties, which is also what the client exposes — a mutable attribute in the
    protocol would refuse the real class, since a settable member cannot be satisfied by one
    that is only gettable.
    """

    @property
    def request_count(self) -> int: ...
    @property
    def cache_hits(self) -> int: ...
    @property
    def bytes_downloaded(self) -> int: ...
    @property
    def waited_seconds(self) -> float: ...
    @property
    def robots_denied(self) -> int: ...


def open_run(
    db: Session, scraper_id: str, *, trigger: str, slot: datetime | None = None
) -> ScrapeRun:
    """Start a run row. ``trigger`` is ``scheduled`` or ``manual``; ``slot`` is null for a
    manual one, because there is no planned time it belongs to."""
    run = ScrapeRun(scraper_id=scraper_id, trigger=trigger, slot=slot, started_at=datetime.now(UTC))
    db.add(run)
    db.commit()
    return run


def run_one_user(
    db: Session,
    run: ScrapeRun,
    user_id: int,
    work: Callable[[], DeltaCounters],
    *,
    http_before: HttpCounters,
    http_after: Callable[[], HttpCounters],
) -> str:
    """Do one user's share of ``run`` and record it. Returns the outcome (``ok``/``error``).

    A failure is caught and written, never raised: on a scheduled run the next user still has to
    go, and on a manual one the person who pressed the button deserves the reason recorded
    rather than a stack trace in a background task nobody reads.
    """
    ulog = ScrapeUserLog(run_id=run.run_id, user_id=user_id, started_at=datetime.now(UTC))
    db.add(ulog)
    outcome = "ok"
    try:
        delta = work()
        ulog.products_found = delta.found
        ulog.products_new = delta.new
        ulog.price_changes = delta.price_changes
        run.products_removed += delta.removed
        # What the scraper filtered out before delivering (9.B5): only the plugin knows, the
        # catalog service is handed the survivors.
        run.products_excluded += delta.excluded
        ulog.status = "ok"
    except Exception as exc:
        log.exception("scrape failed: %s user %s", run.scraper_id, user_id)
        ulog.status = "error"
        ulog.error_message = str(exc)[:500]
        outcome = "error"
    requests_after, hits_after = http_after()
    ulog.http_requests = requests_after - http_before[0]
    ulog.cache_hits = hits_after - http_before[1]
    ulog.finished_at = datetime.now(UTC)
    run.users_processed += 1
    run.products_found += ulog.products_found
    run.products_new += ulog.products_new
    run.price_changes += ulog.price_changes
    run.http_requests += ulog.http_requests
    run.cache_hits += ulog.cache_hits
    db.commit()
    return outcome


def aggregate_status(outcomes: list[str], timed_out: bool) -> str:
    """Run status from the per-user outcomes (scheduling-models.md)."""
    if timed_out:
        return "timeout"
    if not outcomes or all(o == "ok" for o in outcomes):
        return "ok"
    if any(o == "ok" for o in outcomes):
        return "partial"
    return "error"


def close_run(
    db: Session,
    run: ScrapeRun,
    outcomes: list[str],
    *,
    timed_out: bool = False,
    bytes_downloaded: int = 0,
    politeness_wait_s: float = 0.0,
    robots_denied: int = 0,
) -> None:
    """Settle the run and fold it into the lifetime counters (9.B6c). Commits.

    The statistics write is wrapped: ``scrape_run`` has retention, so this row is the only
    memory of what a scraper has ever done — but failing to write a statistic must never be the
    thing that breaks the run it was measuring.
    """
    run.status = aggregate_status(outcomes, timed_out)
    run.finished_at = datetime.now(UTC)
    db.commit()
    try:
        record_run(
            db,
            run.scraper_id,
            ok=run.status == "ok",
            seconds=(run.finished_at - run.started_at).total_seconds(),
            http_requests=run.http_requests,
            cache_hits=run.cache_hits,
            bytes_downloaded=bytes_downloaded,
            politeness_wait_s=politeness_wait_s,
            robots_denied=robots_denied,
            products_delivered=run.products_found,
        )
    except Exception:
        log.exception("could not record the lifetime statistics of %s", run.scraper_id)


def record_traffic(db: Session, plugin_id: str, http: HttpTraffic) -> None:
    """Fold the requests of a **non-run** piece of work into the lifetime counters (10.B20).

    Traffic only, no run row: resolving a pasted URL is real work towards the site and has to
    appear in what the installation says it has sent — that is Simone's *"all of it, not only
    the scheduled part"*. But it is not a run: no user delta, no outcome, nothing a Runs page
    could show a row for, and counting it as one would inflate ``runs_total`` with something
    that never ran.

    Call it once per HTTP client, from whoever owns that client's lifetime. Two clients never
    double-count each other because each carries its own totals; calling this twice on the
    **same** client would, which is why it belongs in a ``finally`` beside the client's close.
    """
    try:
        deltas = {
            "http_requests_total": http.request_count,
            "cache_hits_total": http.cache_hits,
            "bytes_downloaded_total": http.bytes_downloaded,
            "politeness_wait_s_total": int(http.waited_seconds),
            "robots_denied_total": http.robots_denied,
        }
        if any(deltas.values()):
            bump(db, plugin_id, deltas)
    except Exception:
        log.exception("could not record the traffic of %s", plugin_id)
