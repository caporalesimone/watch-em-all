"""HTTP client handed to scraper plugins via the Plugin Context (plugin-context.md).

Phase-3 v0, **stdlib only** (no extra runtime dependency): it enforces politeness
(a minimum interval between requests, CTX-R1), a per-request timeout and an
identifiable User-Agent (CTX-R2), counts requests for monitoring (CTX-R3), and
retries a few times with backoff on transient errors (CTX-R4).

Declared simplifications (flow rule #7): politeness/timeout are **constants**
here — the per-scraper admin-configurable values arrive in phase 4; the scrape
cache (CTX-R9) is phase 9; cooperative cancellation (CTX-R5) lands with the
runner (phase 4). The plugin must use *only* this client (SCR-R6): the ritmo,
the counter and (later) the cache are imposed here, not left to the plugin.

HTTP error statuses (4xx/5xx) are returned as an :class:`HttpResponse` (the
caller decides — e.g. a 404 product is "gone"); only network/timeout failures,
after the retries are exhausted, propagate as exceptions.
"""

from __future__ import annotations

import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # type-only: keeps this module free of runtime src.core imports
    from src.core.scrape_cache import ScrapeCache

DEFAULT_USER_AGENT = "watch-em-all/0.3 (+https://github.com/caporalesimone/watch-em-all)"
DEFAULT_TIMEOUT_S = 15.0
DEFAULT_MIN_INTERVAL_S = 1.5
DEFAULT_MAX_RETRIES = 2
DEFAULT_BACKOFF_BASE_S = 0.5
# Transient server statuses worth a retry; 429 is deliberately excluded (it is a
# rate-limit signal — politeness is our job, retrying immediately is wrong).
_RETRY_STATUSES = frozenset({502, 503, 504})


@dataclass
class HttpResponse:
    """A minimal, decoded-on-demand HTTP response (no library types leak out)."""

    status_code: int
    content: bytes
    url: str
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def text(self) -> str:
        """Best-effort UTF-8 text. Scrapers whose pages lie about their charset
        (e.g. one really served as windows-1252) should decode ``content`` themselves."""
        return self.content.decode("utf-8", errors="replace")


class HttpClient:
    """Polite, counted, retrying HTTP client (one per scrape run).

    ``sleep``/``monotonic`` are injectable so tests stay deterministic and fast.
    """

    def __init__(
        self,
        *,
        user_agent: str = DEFAULT_USER_AGENT,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        min_interval_s: float = DEFAULT_MIN_INTERVAL_S,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_base_s: float = DEFAULT_BACKOFF_BASE_S,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        cache: ScrapeCache | None = None,
    ) -> None:
        self._user_agent = user_agent
        self._timeout_s = timeout_s
        self._min_interval_s = min_interval_s
        self._max_retries = max_retries
        self._backoff_base_s = backoff_base_s
        self._sleep = sleep
        self._monotonic = monotonic
        self._last_request_at: float | None = None
        self._request_count = 0
        self._cache = cache  # scrape cache (CTX-R9); None = no caching
        self._cache_hits = 0

    @property
    def request_count(self) -> int:
        """Total HTTP attempts made (retries included) — feeds monitoring (CTX-R3)."""
        return self._request_count

    @property
    def cache_hits(self) -> int:
        """GET requests served from the scrape cache (CTX-R9) — feeds monitoring."""
        return self._cache_hits

    def get(self, url: str, *, headers: dict[str, str] | None = None) -> HttpResponse:
        return self._request("GET", url, headers=headers)

    def post(
        self, url: str, *, data: bytes | None = None, headers: dict[str, str] | None = None
    ) -> HttpResponse:
        return self._request("POST", url, data=data, headers=headers)

    def _respect_politeness(self) -> None:
        if self._last_request_at is not None and self._min_interval_s > 0:
            wait = self._min_interval_s - (self._monotonic() - self._last_request_at)
            if wait > 0:
                self._sleep(wait)

    def _request(
        self,
        method: str,
        url: str,
        *,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> HttpResponse:
        # Scrape cache (CTX-R9): a GET within the half-life is served from cache — no HTTP,
        # no politeness wait — and counted as a hit. POST is never cached.
        if method == "GET" and self._cache is not None and self._cache.enabled:
            cached = self._cache.get(method, url)
            if cached is not None:
                self._cache_hits += 1
                hdrs_hit = {"content-type": cached.content_type} if cached.content_type else {}
                return HttpResponse(
                    status_code=cached.status_code,
                    content=cached.content,
                    url=url,
                    headers=hdrs_hit,
                )

        hdrs = {"User-Agent": self._user_agent}
        if headers:
            hdrs.update(headers)

        self._respect_politeness()
        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            if attempt > 0:  # backoff between retries (politeness already paced the first)
                self._sleep(self._backoff_base_s * (2 ** (attempt - 1)))
            self._request_count += 1
            try:
                req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
                with urllib.request.urlopen(req, timeout=self._timeout_s) as resp:
                    body = resp.read()
                    self._last_request_at = self._monotonic()
                    resp_headers = {k.lower(): v for k, v in resp.headers.items()}
                    # Cache the successful GET result (CTX-R9). Errors (4xx/5xx) take the
                    # HTTPError path below and are never cached.
                    if method == "GET" and self._cache is not None and self._cache.enabled:
                        self._cache.put(
                            method, url, int(resp.status), body, resp_headers.get("content-type")
                        )
                    return HttpResponse(
                        status_code=int(resp.status),
                        content=body,
                        url=resp.geturl(),
                        headers=resp_headers,
                    )
            except urllib.error.HTTPError as exc:
                self._last_request_at = self._monotonic()
                if exc.code in _RETRY_STATUSES and attempt < self._max_retries:
                    last_exc = exc
                    continue
                body = exc.read() if hasattr(exc, "read") else b""
                hdr_items = exc.headers.items() if exc.headers else []
                return HttpResponse(
                    status_code=int(exc.code),
                    content=body,
                    url=url,
                    headers={k.lower(): v for k, v in hdr_items},
                )
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                self._last_request_at = self._monotonic()
                last_exc = exc
                if attempt < self._max_retries:
                    continue
                raise

        # Unreachable: the last iteration either returns or raises. Guard for mypy.
        raise last_exc if last_exc is not None else RuntimeError("http: no attempt made")
