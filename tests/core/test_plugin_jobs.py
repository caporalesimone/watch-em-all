"""The core's book of in-flight plugin jobs (plugin_jobs.py, CTX-R13). C9/C10.

The behaviours here are the ones the plugins used to implement by hand on somebody else's
session, so each test pins a decision rather than a line of code.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from src.core.plugin_jobs import (
    begin_job,
    forget_job,
    is_cancel_requested,
    publish_progress,
    read_progress,
    request_cancel,
)

PLUGIN = "probe"
JOB = "7"


@pytest.fixture(autouse=True)
def _db(tmp_path: object) -> Iterator[None]:
    from src.core.db import create_schema, init_engine

    init_engine(f"sqlite+pysqlite:///{tmp_path}/jobs.db")  # type: ignore[str-bytes-safe]
    create_schema()
    yield


def test_nothing_is_running_reads_as_nothing() -> None:
    assert read_progress(PLUGIN, JOB) is None
    assert is_cancel_requested(PLUGIN, JOB) is False


def test_progress_is_published_and_read_back() -> None:
    begin_job(PLUGIN, JOB, total=21)
    publish_progress(PLUGIN, JOB, done=3, detail="page 3 of 21")

    state = read_progress(PLUGIN, JOB)

    assert state is not None
    assert (state.done, state.total, state.detail) == (3, 21, "page 3 of 21")


def test_a_step_does_not_erase_the_total() -> None:
    """A walk learns its total from page one; every step after that omits it, and omitting has
    to mean "unchanged" or the bar would lose its denominator on the second page."""
    begin_job(PLUGIN, JOB, total=21)
    publish_progress(PLUGIN, JOB, done=1, detail="page 1 of 21")
    publish_progress(PLUGIN, JOB, done=2)

    state = read_progress(PLUGIN, JOB)

    assert state is not None
    assert (state.done, state.total, state.detail) == (2, 21, "page 1 of 21")


def test_a_finished_job_keeps_its_last_progress() -> None:
    """C20: a walk that stopped on page 2 of 21 has to keep saying so afterwards, so the row is
    not deleted when the work ends — which is why `begin` is what resets it."""
    begin_job(PLUGIN, JOB, total=21)
    publish_progress(PLUGIN, JOB, done=2)

    state = read_progress(PLUGIN, JOB)
    assert state is not None and (state.done, state.total) == (2, 21)


def test_beginning_again_clears_a_stale_cancellation() -> None:
    """Otherwise the next attempt would be killed by a request nobody made this time."""
    request_cancel(PLUGIN, JOB)
    assert is_cancel_requested(PLUGIN, JOB) is True

    begin_job(PLUGIN, JOB)

    assert is_cancel_requested(PLUGIN, JOB) is False
    state = read_progress(PLUGIN, JOB)
    assert state is not None and (state.done, state.total, state.detail) == (0, None, None)


def test_a_cancellation_lands_before_any_progress_exists() -> None:
    """The first politeness wait happens before page one has published anything, and that is
    exactly the window a user changes their mind in. Needing an existing row would drop it."""
    request_cancel(PLUGIN, JOB)

    assert is_cancel_requested(PLUGIN, JOB) is True


def test_jobs_of_two_plugins_do_not_collide() -> None:
    """The key is the plugin's own, so two plugins are free to number their jobs the same way."""
    begin_job(PLUGIN, JOB, total=2)
    begin_job("other", JOB, total=99)

    mine = read_progress(PLUGIN, JOB)
    theirs = read_progress("other", JOB)

    assert mine is not None and mine.total == 2
    assert theirs is not None and theirs.total == 99


def test_forgetting_removes_the_entry() -> None:
    begin_job(PLUGIN, JOB, total=2)

    forget_job(PLUGIN, JOB)

    assert read_progress(PLUGIN, JOB) is None
