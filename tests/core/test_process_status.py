"""What a process reports about itself, and how often it is allowed to (PST-R1..R2).

The rate limit is the point of most of this file. The tick that drives the heartbeat is a
feature flag whose floor is **1 second** — right for scheduling responsiveness, wrong for
persistence: a developer lowering it to watch something happen must not turn that into a write
per second, for ever, on a row whose readers tolerate minutes.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.core.models import ProcessStatus
from src.core.process_status import (
    MIN_HEARTBEAT_INTERVAL_S,
    read,
    report,
    reset_rate_limit,
)


@pytest.fixture()
def session(tmp_path: object) -> Iterator[Session]:
    from src.core.db import create_schema, init_engine, new_session

    init_engine(f"sqlite+pysqlite:///{tmp_path}/status.db")
    create_schema()
    reset_rate_limit()  # the limit is per running process, and each test is a fresh scenario
    s = new_session()
    try:
        yield s
    finally:
        s.close()


def _rows(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(ProcessStatus)) or 0


def test_a_process_that_never_reported_reads_as_nothing(session: Session) -> None:
    assert read(session, "worker") is None


def test_reporting_records_the_state(session: Session) -> None:
    assert report(session, "worker", monotonic=0.0) is True

    reported = read(session, "worker")

    assert reported is not None
    assert (reported.process, reported.state, reported.detail) == ("worker", "running", None)
    assert reported.age_s() < 5


def test_the_same_process_keeps_one_row(session: Session) -> None:
    """A heartbeat is a state, not an event. Appended it would be ~525.000 rows a year at the
    default tick, to answer a question that reads exactly one of them."""
    for beat in range(5):
        report(session, "worker", monotonic=beat * MIN_HEARTBEAT_INTERVAL_S)

    assert _rows(session) == 1


def test_a_beat_that_comes_too_soon_is_skipped(session: Session) -> None:
    """The clamp: at the tick's 1s floor this would otherwise be 86.400 writes a day."""
    assert report(session, "worker", monotonic=0.0) is True

    assert report(session, "worker", monotonic=1.0) is False
    assert report(session, "worker", monotonic=MIN_HEARTBEAT_INTERVAL_S - 0.1) is False
    assert report(session, "worker", monotonic=MIN_HEARTBEAT_INTERVAL_S) is True


def test_a_skipped_beat_does_not_move_the_timestamp(session: Session) -> None:
    """Skipping has to be genuinely free — no write, so nothing observable changes."""
    report(session, "worker", monotonic=0.0)
    first = read(session, "worker")
    assert first is not None

    report(session, "worker", monotonic=1.0)
    again = read(session, "worker")

    assert again is not None
    assert again.last_seen_at == first.last_seen_at


def test_a_change_of_state_is_not_rate_limited(session: Session) -> None:
    """News, not repetition: "the worker suspended itself" must not wait out a limit meant for
    a beat that says the same thing as the last one."""
    report(session, "worker", monotonic=0.0)

    wrote = report(
        session, "worker", state="suspended", detail="schema mismatch", monotonic=0.5, force=True
    )

    assert wrote is True
    reported = read(session, "worker")
    assert reported is not None
    assert (reported.state, reported.detail) == ("suspended", "schema mismatch")


def test_two_processes_are_two_rows(session: Session) -> None:
    """The reason the table is not called `worker_heartbeat`: who reports is a name, not a
    schema change."""
    report(session, "worker", monotonic=0.0)
    report(session, "web", monotonic=0.0)

    assert _rows(session) == 2
    worker, web = read(session, "worker"), read(session, "web")
    assert worker is not None and web is not None
    assert {worker.process, web.process} == {"worker", "web"}


def test_the_age_is_what_liveness_is_answered_with(session: Session) -> None:
    report(session, "worker", monotonic=0.0)
    reported = read(session, "worker")
    assert reported is not None

    # Ten minutes later, from a caller's point of view.
    assert reported.age_s(datetime.now(UTC) + timedelta(seconds=600)) == pytest.approx(600, abs=5)


def test_a_write_that_fails_does_not_take_the_caller_down() -> None:
    """A process must not die because it could not say that it is alive.

    A *closed* session is not the way to test this — SQLAlchemy simply opens a new connection on
    next use — so the failure is injected where it would really come from: the query itself.
    """

    class Broken:
        def scalar(self, *_args: object, **_kwargs: object) -> object:
            raise RuntimeError("the database went away")

        def rollback(self) -> None:
            return None

    assert report(cast(Session, Broken()), "worker", monotonic=0.0) is False
