"""API error type with the project's `{detail, code}` envelope (BE-11, api/README).

Raise APIError anywhere in the request path; a single handler in the web app
renders it as `{"detail": ..., "code": ...}` with the right HTTP status.
"""

from __future__ import annotations


class APIError(Exception):
    """An error meant to reach the client as `{detail, code}` + an HTTP status."""

    def __init__(self, status_code: int, code: str, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.code = code
        self.detail = detail
