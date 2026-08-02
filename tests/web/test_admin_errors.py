"""Tests for the admin-only error feed (4.B0+, GET /api/admin/errors).

Admin-facing errors/warnings are admin-only by contract: never on the public
/api/health probe, never to a normal user or an anonymous caller.
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _admin_token(client: TestClient) -> str:
    # Bootstrap admin starts with a forced change; clear it, then log in again so the
    # token is past the must-change gate require_admin enforces.
    login = client.post("/api/auth/login", json={"username": "admin", "password": "initpass123"})
    access = login.json()["access_token"]
    client.post(
        "/api/auth/change-password",
        json={"new_password": "adminpass123"},
        headers=_bearer(access),
    )
    relogin = client.post("/api/auth/login", json={"username": "admin", "password": "adminpass123"})
    return str(relogin.json()["access_token"])


def _user_token(client: TestClient, admin: str) -> str:
    client.post(
        "/api/admin/users",
        json={
            "username": "alice@example.com",
            "first_name": "Alice",
            "last_name": "Doe",
            "role": "user",
            "temp_password": "temp-pass-123",
        },
        headers=_bearer(admin),
    )
    login = client.post(
        "/api/auth/login", json={"username": "alice@example.com", "password": "temp-pass-123"}
    )
    access = login.json()["access_token"]
    client.post(
        "/api/auth/change-password",
        json={"new_password": "alice-pass-123"},
        headers=_bearer(access),
    )
    relogin = client.post(
        "/api/auth/login", json={"username": "alice@example.com", "password": "alice-pass-123"}
    )
    return str(relogin.json()["access_token"])


def test_admin_errors_is_admin_only(client: TestClient) -> None:
    # Anonymous → 401; a normal user → 403. Never exposed off /api/admin.
    assert client.get("/api/admin/errors").status_code == 401
    admin = _admin_token(client)
    user = _user_token(client, admin)
    assert client.get("/api/admin/errors", headers=_bearer(user)).status_code == 403


def test_admin_errors_clean_is_empty(client: TestClient) -> None:
    """Clean means: schema matches, and the worker is reporting. The second half is new — there
    is no worker process in these tests, so one has to be stood in for; without that this feed
    correctly says nobody is scraping anything."""
    from src.core.db import new_session
    from src.core.process_status import report, reset_rate_limit

    session = new_session()
    try:
        reset_rate_limit()
        report(session, "worker")
    finally:
        session.close()

    admin = _admin_token(client)
    resp = client.get("/api/admin/errors", headers=_bearer(admin))
    assert resp.status_code == 200
    # Fresh test DB matches the models, and the conftest leaves the flag off → empty list.
    assert resp.json() == []


def test_a_worker_that_never_reported_is_a_warning(client: TestClient) -> None:
    """The state of a fresh installation whose worker never came up: nothing is being scraped and
    nothing is being delivered, and the symptom on its own ("my prices are stale") points
    nowhere. Not behind a flag, unlike schema drift — this is a fault of the installation."""
    admin = _admin_token(client)

    (error,) = client.get("/api/admin/errors", headers=_bearer(admin)).json()

    assert error["source"] == "worker_status"
    assert error["type"] == "warning"
    assert "never reported" in error["title"]


def test_a_worker_that_stopped_reporting_is_an_error(client: TestClient) -> None:
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import select

    from src.core.db import new_session
    from src.core.models import ProcessStatus
    from src.core.process_status import report, reset_rate_limit

    session = new_session()
    try:
        reset_rate_limit()
        report(session, "worker")
        row = session.scalars(select(ProcessStatus)).one()
        row.last_seen_at = datetime.now(UTC) - timedelta(seconds=600)
        session.commit()
    finally:
        session.close()

    admin = _admin_token(client)
    (error,) = client.get("/api/admin/errors", headers=_bearer(admin)).json()

    assert error["type"] == "error"
    assert "stopped reporting" in error["title"]
    # The age, not a fixed string: the seconds keep passing while the test runs, and asserting
    # "600s" made this fail the moment the suite was busy enough to reach 601.
    (seconds,) = re.findall(r"Last seen (\d+)s ago", error["description"])
    assert int(seconds) >= 600
    assert "not running" in error["description"]  # says the consequence, not just the fact


def test_a_suspended_worker_reports_why(client: TestClient) -> None:
    """A worker that stopped itself is a different fault from one that died, and the reason it
    recorded is the whole value — an admin should not have to read container logs for it."""
    from src.core.db import new_session
    from src.core.process_status import report, reset_rate_limit

    session = new_session()
    try:
        reset_rate_limit()
        report(session, "worker", state="suspended", detail="the schema does not match", force=True)
    finally:
        session.close()

    admin = _admin_token(client)
    (error,) = client.get("/api/admin/errors", headers=_bearer(admin)).json()

    assert error["type"] == "error"
    assert "suspended itself" in error["title"]
    assert error["description"] == "the schema does not match"
