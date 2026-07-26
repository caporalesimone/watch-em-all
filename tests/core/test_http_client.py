"""Tests for the scraper HTTP client (``src/core/http.py``).

Politeness, request counter, retry-with-backoff, ``robots.txt`` compliance and the
per-run cookie session (CTX-R1/R3/R4/R10) verified against a local mock server
(phase-03 3.B5). ``sleep``/``monotonic`` are injected so the tests are deterministic
and never actually wait.

The tests that are not *about* robots pass ``respect_robots=False``: otherwise every
one of them would begin with a ``/robots.txt`` request against the mock server, which
would both skew the request counters and hand the handler a path it was not written for.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from src.core.http import HttpClient, RobotsDenied


class _Server:
    """A throwaway HTTP server on an ephemeral port, as a context manager."""

    def __init__(self, handler: type[BaseHTTPRequestHandler]) -> None:
        self._srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self._thread = threading.Thread(target=self._srv.serve_forever, daemon=True)

    def __enter__(self) -> str:
        self._thread.start()
        return f"http://127.0.0.1:{self._srv.server_address[1]}"

    def __exit__(self, *exc: object) -> None:
        self._srv.shutdown()
        self._srv.server_close()
        self._thread.join(timeout=2)


def _noop(_seconds: float) -> None:
    pass


def test_retry_on_transient_status_then_success() -> None:
    state: dict[str, int] = {"hits": 0}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            state["hits"] += 1
            self.send_response(503 if state["hits"] == 1 else 200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, fmt: str, *args: Any) -> None:
            return

    with _Server(Handler) as base:
        client = HttpClient(
            min_interval_s=0.0,
            max_retries=2,
            backoff_base_s=0.0,
            sleep=_noop,
            respect_robots=False,
        )
        resp = client.get(base + "/")

    assert resp.status_code == 200
    assert resp.content == b"ok"
    assert state["hits"] == 2  # 503 then 200
    assert client.request_count == 2  # both attempts counted (CTX-R3)


def test_exhausted_retries_return_error_response() -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(503)
            self.end_headers()
            self.wfile.write(b"busy")

        def log_message(self, fmt: str, *args: Any) -> None:
            return

    with _Server(Handler) as base:
        client = HttpClient(
            min_interval_s=0.0,
            max_retries=1,
            backoff_base_s=0.0,
            sleep=_noop,
            respect_robots=False,
        )
        resp = client.get(base + "/")

    assert resp.status_code == 503  # transient but persistent → returned, not raised
    assert client.request_count == 2  # first + one retry


def test_non_transient_status_returned_without_retry() -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"nope")

        def log_message(self, fmt: str, *args: Any) -> None:
            return

    with _Server(Handler) as base:
        client = HttpClient(min_interval_s=0.0, max_retries=2, sleep=_noop, respect_robots=False)
        resp = client.get(base + "/")

    assert resp.status_code == 404
    assert resp.content == b"nope"
    assert client.request_count == 1  # 404 is not transient: no retry


def test_politeness_waits_between_requests() -> None:
    slept: list[float] = []
    clock: dict[str, float] = {"t": 100.0}  # frozen clock → elapsed is always 0

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"x")

        def log_message(self, fmt: str, *args: Any) -> None:
            return

    with _Server(Handler) as base:
        client = HttpClient(
            min_interval_s=1.5,
            max_retries=0,
            sleep=slept.append,
            monotonic=lambda: clock["t"],
            respect_robots=False,
        )
        client.get(base + "/")  # first request: no wait
        client.get(base + "/")  # second request: must wait the full interval

    assert slept == [1.5]


class _RobotsHandler(BaseHTTPRequestHandler):
    """Serves ``/robots.txt`` from the class attributes and a trivial page for anything else."""

    robots: bytes = b"User-agent: *\n"
    robots_status: int = 200

    def do_GET(self) -> None:
        if self.path == "/robots.txt":
            self.send_response(self.robots_status)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(self.robots)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"page")

    def log_message(self, fmt: str, *args: Any) -> None:
        return


def test_crawl_delay_raises_the_politeness_floor() -> None:
    """CTX-R10: the site's Crawl-delay wins when it is slower than what we configured."""
    slept: list[float] = []
    clock: dict[str, float] = {"t": 0.0}  # frozen → elapsed is always 0

    class Handler(_RobotsHandler):
        robots = b"User-agent: *\nCrawl-delay: 20\n"

    with _Server(Handler) as base:
        client = HttpClient(
            min_interval_s=1.5, max_retries=0, sleep=slept.append, monotonic=lambda: clock["t"]
        )
        resp = client.get(base + "/a")
        client.get(base + "/b")
        policy = client.robots_for(base + "/a")

    assert resp.status_code == 200
    # Between the two pages we wait the site's 20 s, not our configured 1.5 s.
    assert slept == [20.0]
    assert policy.crawl_delay == 20.0
    assert client.request_count == 3  # robots.txt counts as a request too (CTX-R3)


def test_configured_delay_wins_when_slower_than_crawl_delay() -> None:
    slept: list[float] = []
    clock: dict[str, float] = {"t": 0.0}

    class Handler(_RobotsHandler):
        robots = b"User-agent: *\nCrawl-delay: 2\n"

    with _Server(Handler) as base:
        client = HttpClient(
            min_interval_s=11.0, max_retries=0, sleep=slept.append, monotonic=lambda: clock["t"]
        )
        client.get(base + "/a")
        client.get(base + "/b")

    assert slept == [11.0]  # never faster than either value


def test_robots_fetch_does_not_start_the_politeness_clock() -> None:
    """Every crawler treats robots.txt as exempt from the delay it declares. Charging for
    it would make the first page of a run wait the full interval for nothing — very visible
    on the single-page scrape that resolves a watch as a user adds it."""
    slept: list[float] = []
    clock: dict[str, float] = {"t": 0.0}

    class Handler(_RobotsHandler):
        robots = b"User-agent: *\nCrawl-delay: 30\n"

    with _Server(Handler) as base:
        client = HttpClient(
            min_interval_s=11.0, max_retries=0, sleep=slept.append, monotonic=lambda: clock["t"]
        )
        client.get(base + "/only-page")

    assert slept == []  # robots.txt then the page, back to back


def test_disallowed_path_is_never_requested() -> None:
    seen: list[str] = []

    class Handler(_RobotsHandler):
        robots = b"User-agent: *\nDisallow: /private\n"

        def do_GET(self) -> None:
            seen.append(self.path)
            super().do_GET()

    with _Server(Handler) as base:
        client = HttpClient(min_interval_s=0.0, sleep=_noop)
        with pytest.raises(RobotsDenied):
            client.get(base + "/private/x")
        assert client.get(base + "/public").status_code == 200

    assert "/private/x" not in seen  # blocked before any socket was opened


def test_unreadable_robots_disallows_the_whole_site() -> None:
    """RFC 9309 §2.3.1: a 5xx on robots.txt means assume everything is off-limits."""

    class Handler(_RobotsHandler):
        robots_status = 500
        robots = b"boom"

    with _Server(Handler) as base:
        client = HttpClient(min_interval_s=0.0, sleep=_noop)
        with pytest.raises(RobotsDenied):
            client.get(base + "/p")


def test_missing_robots_allows_everything() -> None:
    """A 4xx means no policy is published, not that we are forbidden."""

    class Handler(_RobotsHandler):
        robots_status = 404
        robots = b"not here"

    with _Server(Handler) as base:
        client = HttpClient(min_interval_s=0.0, sleep=_noop)
        assert client.get(base + "/p").status_code == 200


def test_robots_is_fetched_once_per_origin() -> None:
    seen: list[str] = []

    class Handler(_RobotsHandler):
        def do_GET(self) -> None:
            seen.append(self.path)
            super().do_GET()

    with _Server(Handler) as base:
        client = HttpClient(min_interval_s=0.0, sleep=_noop)
        client.get(base + "/a")
        client.get(base + "/b")

    assert seen.count("/robots.txt") == 1  # one policy per origin per run


def test_session_cookies_survive_across_requests() -> None:
    """Without this, a site that clears a gate per *session* gates us on every page."""
    sent: list[str] = []

    class Handler(_RobotsHandler):
        def do_GET(self) -> None:
            if self.path == "/robots.txt":
                super().do_GET()
                return
            sent.append(self.headers.get("Cookie") or "")
            self.send_response(200)
            self.send_header("Set-Cookie", "ASPSESSIONID=abc; path=/")
            self.end_headers()
            self.wfile.write(b"page")

    with _Server(Handler) as base:
        client = HttpClient(min_interval_s=0.0, sleep=_noop)
        client.get(base + "/one")
        client.get(base + "/two")
        held = client.cookies

    assert sent == ["", "ASPSESSIONID=abc"]  # the second request carries the session
    assert held == 1


def test_user_agent_follows_the_running_version(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """CTX-R2: the UA is built from the version file baked at build, not from a literal —
    the literal it replaced had been announcing 0.3 since phase 3."""
    from src.core import config as config_mod
    from src.core.http import default_user_agent

    contact = "+https://github.com/caporalesimone/watch-em-all"

    version_file = tmp_path / "VERSION"
    version_file.write_text("0.8.1-3-gabc1234\n", encoding="utf-8")
    monkeypatch.setattr(config_mod, "VERSION_PATH", str(version_file))
    assert default_user_agent() == f"watch-em-all/0.8.1-3-gabc1234 ({contact})"

    # Read on demand, not frozen at import: a new build is reflected immediately.
    version_file.write_text("0.9.0\n", encoding="utf-8")
    assert default_user_agent() == f"watch-em-all/0.9.0 ({contact})"

    # No version file (a stray local run) degrades honestly instead of lying.
    monkeypatch.setattr(config_mod, "VERSION_PATH", str(tmp_path / "missing"))
    assert default_user_agent() == f"watch-em-all/0.0.0-unknown ({contact})"

    # The product token is what robots.txt User-agent lines match on: it must not move.
    assert default_user_agent().split("/")[0] == "watch-em-all"


def test_client_sends_the_derived_user_agent() -> None:
    seen: list[str] = []

    class Handler(_RobotsHandler):
        def do_GET(self) -> None:
            seen.append(self.headers.get("User-Agent") or "")
            super().do_GET()

    with _Server(Handler) as base:
        client = HttpClient(min_interval_s=0.0, sleep=_noop)
        client.get(base + "/p")

    # Both the robots.txt fetch and the page itself identify us the same way.
    assert len(seen) == 2
    assert all(ua.startswith("watch-em-all/") for ua in seen)
    assert all("github.com/caporalesimone/watch-em-all" in ua for ua in seen)
