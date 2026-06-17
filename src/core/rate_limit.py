"""In-memory login rate limiter (AUTH-R6).

A per-process sliding window keyed by IP+username. Fits the self-hosted ≤5-user
posture (no shared store); a single web process is the norm. Thread-safe because
FastAPI runs sync endpoints in a threadpool (BE-21).
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, max_attempts: int = 5, window_seconds: float = 60.0) -> None:
        self._max = max_attempts
        self._window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, *, now: float | None = None) -> bool:
        """Record an attempt; return True if within the limit, False if over it."""
        ts = time.monotonic() if now is None else now
        with self._lock:
            window = self._hits[key]
            while window and window[0] <= ts - self._window:
                window.popleft()
            if len(window) >= self._max:
                return False
            window.append(ts)
            return True

    def reset(self, key: str) -> None:
        """Clear the history for a key (called on a successful login)."""
        with self._lock:
            self._hits.pop(key, None)
