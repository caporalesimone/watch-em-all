"""HTTP client handed to scraper plugins via the Plugin Context (plugin-context.md).

Stdlib only (no extra runtime dependency). It enforces politeness (a minimum interval
between requests, CTX-R1), a per-request timeout and an identifiable User-Agent (CTX-R2),
counts requests for monitoring (CTX-R3), retries a few times with backoff on transient
errors (CTX-R4), serves repeated GETs from the scrape cache (CTX-R9) and obeys the site's
``robots.txt`` (CTX-R10).

Two properties are deliberate, not incidental:

- **The plugin cannot opt out.** Politeness, ``robots.txt`` and the request counter live
  here, not in the scrapers (SCR-R6). An API a plugin must remember to call is an API a
  plugin will eventually forget to call, and the failure would be silent.
- **A retry is a request too.** The politeness floor is re-applied before every attempt,
  so a retry can never fire sooner than the site allows. Before this, a retry went out
  half a second after the previous one no matter what the site had asked for.

``robots.txt`` is fetched once per origin per client instance (a client instance lives for
one scrape run) and is exempt from its own ``Crawl-delay``, per convention. HTTP error
statuses (4xx/5xx) are returned as an :class:`HttpResponse` — the caller decides, e.g. a
404 product is "gone". Only network/timeout failures, after the retries are exhausted,
propagate as exceptions; a path forbidden by ``robots.txt`` raises :class:`RobotsDenied`.
"""

from __future__ import annotations

import logging
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from http.cookiejar import CookieJar
from typing import TYPE_CHECKING

from src.core.config import read_version
from src.core.robots import (
    RobotsPolicy,
    origin_of,
    policy_from_response,
    robots_url,
    unreachable_policy,
)

if TYPE_CHECKING:  # type-only: keeps this module free of runtime src.core imports
    from src.core.scrape_cache import ScrapeCache

USER_AGENT_PRODUCT = "watch-em-all"
USER_AGENT_CONTACT = "+https://github.com/caporalesimone/watch-em-all"
DEFAULT_TIMEOUT_S = 15.0
# Politeness floor between two requests to the same site. Sites state their own rate
# in ``robots.txt`` (``Crawl-delay``); this default sits just above the slowest value
# we have met in the wild (Dragon Store asks 10 s) so an unconfigured scraper is
# compliant by default rather than by luck.
DEFAULT_MIN_INTERVAL_S = 11.0
DEFAULT_MAX_RETRIES = 2
# A retry is another request to the same host, so the backoff starts at the politeness
# floor — never below it.
DEFAULT_BACKOFF_BASE_S = 11.0
# Transient server statuses worth a retry; 429 is deliberately excluded (it is a
# rate-limit signal — politeness is our job, retrying immediately is wrong).
_RETRY_STATUSES = frozenset({502, 503, 504})

_DEFAULT_LOGGER = logging.getLogger("wea.http")


def default_user_agent() -> str:
    """``watch-em-all/<version> (+repo)`` — who we tell a site we are (CTX-R2).

    The version comes from the **single source of truth**, the file baked at build from
    ``git describe`` (1.T4), and is read **on demand rather than at import**, so the string
    follows the running build. It used to be a literal, and had been announcing ``0.3``
    since phase 3 — five phases of claiming to be something we were not, to sites whose
    operators may well read their logs.

    The product token before the ``/`` is what a ``robots.txt`` ``User-agent:`` line is
    matched against, so it stays ``watch-em-all`` no matter what the version does.
    """
    return f"{USER_AGENT_PRODUCT}/{read_version()} ({USER_AGENT_CONTACT})"


class RobotsDenied(OSError):
    """``robots.txt`` forbids this request: the path is disallowed, or the file itself
    could not be retrieved (RFC 9309 §2.3.1: a 5xx means assume the site is off-limits).

    Deliberately an ``OSError``, so a scraper's existing "fetch failed" handling catches
    it instead of letting it abort a whole run — while staying distinguishable by type.
    """


@dataclass
class HttpResponse:
    """A minimal, decoded-on-demand HTTP response (no library types leak out)."""

    status_code: int
    content: bytes
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    # When the *site* produced this body. ``None`` means "just now, over the network";
    # a value means it came from the scrape cache and is that old. Without this a caller
    # cannot tell a fresh read from one replayed up to a half-life later, and any
    # "last seen" it derives silently reports the replay instead of the observation.
    fetched_at: datetime | None = None

    @property
    def text(self) -> str:
        """Best-effort UTF-8 text. Scrapers whose pages lie about their charset
        (e.g. one really served as windows-1252) should decode ``content`` themselves."""
        return self.content.decode("utf-8", errors="replace")


class HttpClient:
    """Polite, counted, retrying, robots-abiding client (one per scrape run).

    ``sleep``/``monotonic`` are injectable so tests stay deterministic and fast.
    """

    def __init__(
        self,
        *,
        user_agent: str | None = None,  # None -> default_user_agent(), resolved per client
        timeout_s: float = DEFAULT_TIMEOUT_S,
        min_interval_s: float = DEFAULT_MIN_INTERVAL_S,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_base_s: float = DEFAULT_BACKOFF_BASE_S,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        cache: ScrapeCache | None = None,
        logger: logging.Logger | None = None,
        respect_robots: bool = True,
    ) -> None:
        self._user_agent = user_agent or default_user_agent()
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
        self._log = logger or _DEFAULT_LOGGER
        # One session for the whole run: some sites (Dragon Store) gate the first request
        # of a session behind an interstitial, and without a jar we would discard the
        # cleared session and be gated again on every single page.
        self._jar = CookieJar()
        self._opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self._jar))
        self._had_cookies = False
        self._respect_robots = respect_robots
        self._robots: dict[str, RobotsPolicy] = {}  # per origin, for this run

    @property
    def request_count(self) -> int:
        """Total HTTP attempts made (retries and robots.txt included) — CTX-R3."""
        return self._request_count

    @property
    def cache_hits(self) -> int:
        """GET requests served from the scrape cache (CTX-R9) — feeds monitoring."""
        return self._cache_hits

    @property
    def cookies(self) -> int:
        """Cookies currently held for this run's session (debugging aid)."""
        return len(self._jar)

    def get(self, url: str, *, headers: dict[str, str] | None = None) -> HttpResponse:
        return self._request("GET", url, headers=headers)

    def post(
        self, url: str, *, data: bytes | None = None, headers: dict[str, str] | None = None
    ) -> HttpResponse:
        return self._request("POST", url, data=data, headers=headers)

    def forget(self, url: str) -> None:
        """Drop this URL's cached entry (CTX-R9). For when a 200 turns out to be worthless
        — an anti-bot interstitial or a soft error page — which must not be replayed from
        cache for the whole half-life."""
        if self._cache is None or not self._cache.enabled:
            return
        if self._cache.delete("GET", url):
            self._log.info("http: dropped %s from the scrape cache", url)

    # --- robots.txt (CTX-R10) ---
    def robots_for(self, url: str) -> RobotsPolicy:
        """The policy for this URL's origin, fetched once per origin per run and logged
        so a reader of the logs can see exactly what we believe the site allows."""
        origin = origin_of(url)
        cached = self._robots.get(origin)
        if cached is not None:
            return cached

        target = robots_url(origin)
        self._log.info("robots: reading %s", target)
        try:
            status, body = self._raw_get(target)
        except OSError as exc:
            policy = unreachable_policy(origin, self._user_agent)
            self._log.error(
                "robots: %s could not be fetched (%s) → treating the whole site as "
                "disallowed (RFC 9309 §2.3.1)",
                target,
                exc,
            )
            self._robots[origin] = policy
            return policy

        policy = policy_from_response(origin, self._user_agent, status_code=status, body=body)
        self._log_policy(target, status, len(body), policy)
        self._robots[origin] = policy
        return policy

    def _log_policy(self, target: str, status: int, size: int, policy: RobotsPolicy) -> None:
        """One INFO line per fact, so the effective rate is never a mystery."""
        self._log.info("robots: %s → HTTP %s, %s bytes", target, status, size)
        if not policy.reachable:
            self._log.error(
                "robots: %s returned HTTP %s → treating the whole site as disallowed "
                "(RFC 9309 §2.3.1)",
                target,
                status,
            )
            return
        if policy.allow_all:
            self._log.warning(
                "robots: no policy published at %s (HTTP %s) → everything allowed, "
                "keeping the configured %.1fs delay",
                target,
                status,
                self._min_interval_s,
            )
            return

        self._log.info(
            "robots: parsed for User-Agent %r → %s Disallow rule(s)",
            self._user_agent,
            policy.disallow_rules,
        )
        if policy.crawl_delay is None:
            self._log.info(
                "robots: no Crawl-delay declared → keeping the configured %.1fs delay",
                self._min_interval_s,
            )
            return

        effective = policy.interval_floor(self._min_interval_s)
        self._log.info(
            "robots: Crawl-delay %.1fs declared, configured %.1fs → using %.1fs between requests",
            policy.crawl_delay,
            self._min_interval_s,
            effective,
        )
        if policy.crawl_delay > self._min_interval_s:
            self._log.warning(
                "robots: %s asks for %.1fs, more than our configured %.1fs — the site's "
                "value wins; raise politeness_delay_ms to silence this",
                policy.origin,
                policy.crawl_delay,
                self._min_interval_s,
            )

    def _raw_get(self, url: str) -> tuple[int, bytes]:
        """A single bare GET: no cache, no politeness, no robots check — used to fetch
        ``robots.txt`` itself, which cannot be gated by its own rules.

        It is counted (CTX-R3) but deliberately does **not** stamp the politeness clock:
        every crawler treats robots.txt as exempt from the delay it declares, and charging
        for it would mean the first real page of a run waits the full interval for nothing
        — very visible on the one-page scrape that resolves a watch as the user adds it.
        """
        req = urllib.request.Request(url, headers={"User-Agent": self._user_agent}, method="GET")
        self._request_count += 1
        try:
            with self._opener.open(req, timeout=self._timeout_s) as resp:
                return int(resp.status), resp.read()
        except urllib.error.HTTPError as exc:
            return int(exc.code), exc.read() if hasattr(exc, "read") else b""

    # --- politeness (CTX-R1) ---
    def _wait_before(self, attempt: int, interval_s: float) -> None:
        """Sleep whatever is still owed before the next attempt: the politeness interval
        since the previous request, and — from the second attempt on — at least the
        backoff. Never less than the site's floor."""
        waits = [0.0]
        if self._last_request_at is not None and interval_s > 0:
            waits.append(interval_s - (self._monotonic() - self._last_request_at))
        if attempt > 0:
            waits.append(self._backoff_base_s * (2 ** (attempt - 1)))
        wait = max(waits)
        if wait > 0:
            self._sleep(wait)

    def _note_cookies(self) -> None:
        if not self._had_cookies and len(self._jar) > 0:
            self._had_cookies = True
            self._log.info("http: session established (%s cookie(s) held)", len(self._jar))

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
                self._log.info("http: %s served from the scrape cache", url)
                hdrs_hit = {"content-type": cached.content_type} if cached.content_type else {}
                return HttpResponse(
                    status_code=cached.status_code,
                    content=cached.content,
                    url=url,
                    headers=hdrs_hit,
                    fetched_at=cached.fetched_at,
                )

        interval_s = self._min_interval_s
        if self._respect_robots:
            policy = self.robots_for(url)
            if not policy.allows(url):
                self._log.error("robots: %s is disallowed for us — not requesting it", url)
                raise RobotsDenied(f"robots.txt disallows {url}")
            interval_s = policy.interval_floor(self._min_interval_s)

        hdrs = {"User-Agent": self._user_agent}
        if headers:
            hdrs.update(headers)

        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            self._wait_before(attempt, interval_s)
            if attempt > 0:
                self._log.warning(
                    "http: retrying %s %s (attempt %s of %s)",
                    method,
                    url,
                    attempt + 1,
                    self._max_retries + 1,
                )
            self._request_count += 1
            try:
                req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
                with self._opener.open(req, timeout=self._timeout_s) as resp:
                    body = resp.read()
                    self._last_request_at = self._monotonic()
                    self._note_cookies()
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
                self._note_cookies()
                if exc.code in _RETRY_STATUSES and attempt < self._max_retries:
                    self._log.warning("http: %s returned HTTP %s (transient)", url, exc.code)
                    last_exc = exc
                    continue
                if exc.code == 429:
                    self._log.error(
                        "http: %s returned HTTP 429 Too Many Requests — we are being "
                        "rate-limited; not retrying",
                        url,
                    )
                else:
                    self._log.warning("http: %s returned HTTP %s", url, exc.code)
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
                    self._log.warning("http: %s %s failed (%s)", method, url, exc)
                    continue
                self._log.error(
                    "http: %s %s failed after %s attempt(s): %s",
                    method,
                    url,
                    self._max_retries + 1,
                    exc,
                )
                raise

        # Unreachable: the last iteration either returns or raises. Guard for mypy.
        raise last_exc if last_exc is not None else RuntimeError("http: no attempt made")
