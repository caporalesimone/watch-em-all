"""Serial scraper runner (4.B4): one scraper at a time (SCHED-R6).

A FIFO queue drained by a single background thread, so the dispatcher's tick never
blocks (CRON-R5) and no two scrapers ever run concurrently. A submission for a scraper
already queued or running is dropped (so a slow scraper whose slot fires again just
keeps its place, it doesn't pile up).
"""

from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable
from datetime import datetime

log = logging.getLogger("wea.worker.runner")

# (scraper_id, slot, trigger) -> run it
RunJob = Callable[[str, datetime, str], None]


class Runner:
    """A single-consumer FIFO job runner."""

    def __init__(self, run_job: RunJob) -> None:
        self._run_job = run_job
        self._queue: queue.Queue[tuple[str, datetime, str]] = queue.Queue()
        self._pending: set[str] = set()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._drain, name="scraper-runner", daemon=True)
        self._thread.start()

    def submit(self, scraper_id: str, slot: datetime, trigger: str = "scheduled") -> bool:
        """Enqueue a run unless this scraper is already queued/running. Returns whether
        it was enqueued."""
        with self._lock:
            if scraper_id in self._pending:
                return False
            self._pending.add(scraper_id)
        self._queue.put((scraper_id, slot, trigger))
        return True

    def join(self) -> None:
        """Block until the queue is drained (tests)."""
        self._queue.join()

    def _drain(self) -> None:
        while True:
            scraper_id, slot, trigger = self._queue.get()
            try:
                self._run_job(scraper_id, slot, trigger)
            except Exception:
                log.exception("runner: job for %s failed", scraper_id)
            finally:
                with self._lock:
                    self._pending.discard(scraper_id)
                self._queue.task_done()
