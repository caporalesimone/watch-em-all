"""Tests for the scraper HTTP client (``src/core/http.py``).

Politeness, request counter and retry-with-backoff (CTX-R1/R3/R4) verified
against a local mock server (phase-03 3.B5). ``sleep``/``monotonic`` are injected
so the tests are deterministic and never actually wait.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from src.core.http import HttpClient


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
        client = HttpClient(min_interval_s=0.0, max_retries=2, backoff_base_s=0.0, sleep=_noop)
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
        client = HttpClient(min_interval_s=0.0, max_retries=1, backoff_base_s=0.0, sleep=_noop)
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
        client = HttpClient(min_interval_s=0.0, max_retries=2, sleep=_noop)
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
        )
        client.get(base + "/")  # first request: no wait
        client.get(base + "/")  # second request: must wait the full interval

    assert slept == [1.5]
