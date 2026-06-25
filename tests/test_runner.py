"""Tests for the serial scraper runner (4.B4)."""

from __future__ import annotations

import threading
from datetime import UTC, datetime

from src.worker.runner import Runner

SLOT = datetime(2026, 6, 25, 6, 0, tzinfo=UTC)


def test_runs_jobs_serially_in_submission_order() -> None:
    order: list[str] = []
    lock = threading.Lock()

    def job(scraper_id: str, slot: datetime, trigger: str) -> None:
        with lock:
            order.append(scraper_id)

    runner = Runner(job)
    runner.start()
    assert runner.submit("a", SLOT) is True
    assert runner.submit("b", SLOT) is True
    runner.join()
    assert order == ["a", "b"]


def test_dedups_a_scraper_already_running() -> None:
    started = threading.Event()
    release = threading.Event()

    def job(scraper_id: str, slot: datetime, trigger: str) -> None:
        started.set()
        release.wait(timeout=2)

    runner = Runner(job)
    runner.start()
    assert runner.submit("a", SLOT) is True
    assert started.wait(timeout=2)  # 'a' is running and still pending
    assert runner.submit("a", SLOT) is False  # deduped while pending/running
    release.set()
    runner.join()
