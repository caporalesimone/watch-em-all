"""Per-scraper run lock (4.B5, SCHED-R4): never two runs of the same scraper at once.

On PostgreSQL a session-level advisory lock (a deterministic 64-bit key from the
``plugin_id``) coordinates **across containers** — the worker's serial runner and the
web's scrape-now share it. Elsewhere (SQLite in tests, single process) a process-local
lock is enough. Always **non-blocking**: a held lock means the caller skips (a scheduled
run) or is refused (a manual scrape-now → 409).
"""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, text
from sqlalchemy.engine import Connection

_local_locks: dict[str, threading.Lock] = {}
_local_guard = threading.Lock()


def _key(plugin_id: str) -> int:
    # Deterministic signed 64-bit key for pg advisory locks (never the built-in hash()).
    return int.from_bytes(
        hashlib.sha256(plugin_id.encode("utf-8")).digest()[:8], "big", signed=True
    )


class ScraperLock:
    """A held per-scraper lock. Call :meth:`release` when the run finishes."""

    def __init__(
        self,
        *,
        conn: Connection | None = None,
        key: int | None = None,
        local: threading.Lock | None = None,
    ) -> None:
        self._conn = conn
        self._key = key
        self._local = local

    def release(self) -> None:
        if self._conn is not None and self._key is not None:
            try:
                self._conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": self._key})
            finally:
                self._conn.close()
            self._conn = None
        if self._local is not None:
            self._local.release()
            self._local = None


def acquire_scraper_lock(engine: Engine, plugin_id: str) -> ScraperLock | None:
    """Try to take the lock without blocking. Returns a held lock, or ``None`` if another
    holder already has it."""
    if engine.dialect.name == "postgresql":
        conn = engine.connect()
        key = _key(plugin_id)
        got = conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": key}).scalar()
        if not got:
            conn.close()
            return None
        return ScraperLock(conn=conn, key=key)
    with _local_guard:
        local = _local_locks.setdefault(plugin_id, threading.Lock())
    if not local.acquire(blocking=False):
        return None
    return ScraperLock(local=local)


@contextmanager
def scraper_lock(engine: Engine, plugin_id: str) -> Iterator[bool]:
    """Context manager for synchronous callers (the runner): yields whether acquired."""
    lock = acquire_scraper_lock(engine, plugin_id)
    try:
        yield lock is not None
    finally:
        if lock is not None:
            lock.release()
