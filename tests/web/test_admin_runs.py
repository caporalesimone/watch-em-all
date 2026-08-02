"""Run monitoring for the admin (10.B6): the list, and the drill-down that names names."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from src.core.db import new_session
from src.core.models import ScrapeRun, ScrapeUserLog

NOW = datetime(2026, 8, 2, 6, 0, tzinfo=UTC)


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _admin_token(client: TestClient) -> str:
    login = client.post("/api/auth/login", json={"username": "admin", "password": "initpass123"})
    access = login.json()["access_token"]
    client.post(
        "/api/auth/change-password", json={"new_password": "adminpass123"}, headers=_bearer(access)
    )
    relogin = client.post("/api/auth/login", json={"username": "admin", "password": "adminpass123"})
    return str(relogin.json()["access_token"])


def _seed(runs: list[tuple[str, str, int]]) -> list[int]:
    """(scraper, status, minutes-ago) -> run ids, oldest first."""
    session = new_session()
    ids = []
    try:
        for scraper, status, ago in runs:
            run = ScrapeRun(
                scraper_id=scraper,
                trigger="scheduled",
                started_at=NOW - timedelta(minutes=ago),
                finished_at=NOW - timedelta(minutes=ago - 1),
                status=status,
                users_processed=2,
            )
            session.add(run)
            session.flush()
            ids.append(int(run.run_id))
        session.commit()
    finally:
        session.close()
    return ids


def test_runs_come_back_newest_first_and_filter(client: TestClient) -> None:
    token = _admin_token(client)
    _seed([("dragon_store", "ok", 30), ("dragon_store", "error", 10), ("other", "ok", 20)])

    page = client.get("/api/admin/runs", headers=_bearer(token)).json()
    assert page["total"] == 3
    assert [r["status"] for r in page["items"]] == ["error", "ok", "ok"], "newest first"

    only = client.get("/api/admin/runs?scraper_id=dragon_store", headers=_bearer(token)).json()
    assert only["total"] == 2
    failed = client.get("/api/admin/runs?status=error", headers=_bearer(token)).json()
    assert failed["total"] == 1


def test_paging_reports_the_full_total_not_the_page(client: TestClient) -> None:
    token = _admin_token(client)
    _seed([("dragon_store", "ok", n) for n in range(1, 6)])
    page = client.get("/api/admin/runs?page=1&page_size=2", headers=_bearer(token)).json()
    assert len(page["items"]) == 2
    assert page["total"] == 5, "the count is of everything, or paging cannot be drawn"


def test_the_drill_down_puts_the_failure_first_and_names_the_user(client: TestClient) -> None:
    token = _admin_token(client)
    created = client.post(
        "/api/admin/users",
        json={
            "username": "alice@example.com",
            "first_name": "A",
            "last_name": "R",
            "role": "user",
        },
        headers=_bearer(token),
    ).json()
    (run_id,) = _seed([("dragon_store", "partial", 5)])

    session = new_session()
    try:
        session.add(
            ScrapeUserLog(run_id=run_id, user_id=1, started_at=NOW, status="ok", products_found=3)
        )
        session.add(
            ScrapeUserLog(
                run_id=run_id,
                user_id=created["id"],
                started_at=NOW + timedelta(seconds=1),
                status="error",
                error_message="the site said no",
            )
        )
        session.commit()
    finally:
        session.close()

    rows = client.get(f"/api/admin/runs/{run_id}", headers=_bearer(token)).json()
    # Failures first: on a partial run, finding them is the whole reason to open this.
    assert rows[0]["status"] == "error"
    assert rows[0]["username"] == "alice@example.com", "an id does not answer 'who'"
    assert rows[0]["error_message"] == "the site said no"


def test_an_unknown_run_is_a_404_and_the_routes_are_admin_only(client: TestClient) -> None:
    token = _admin_token(client)
    assert client.get("/api/admin/runs/9999", headers=_bearer(token)).status_code == 404
    assert client.get("/api/admin/runs").status_code == 401


def test_the_calendar_lists_the_days_planned_runs_and_marks_the_suspended(
    client: TestClient,
) -> None:
    """10.B18: a day that looks empty because everything is off is a different problem from
    a day nothing was ever scheduled for, so suspended scrapers are returned and marked."""
    token = _admin_token(client)
    client.put(
        "/api/admin/scrapers/dragon_store",
        json={"times": ["14:30", "02:00"], "enabled": False},
        headers=_bearer(token),
    )
    day = client.get("/api/admin/scrapers/calendar?date=2026-08-05", headers=_bearer(token)).json()
    assert day["date"] == "2026-08-05"
    times = [slot["at"][11:16] for slot in day["slots"]]
    assert times == ["02:00", "14:30"], "sorted by clock, not by how they were typed"
    assert all(slot["enabled"] is False for slot in day["slots"])
    # Nothing has run, so there is no duration to average — and null says that, where a
    # default would draw a confident block around a guess.
    assert all(slot["avg_seconds"] is None for slot in day["slots"])


def test_the_calendar_reports_how_long_recent_runs_took(client: TestClient) -> None:
    token = _admin_token(client)
    client.put(
        "/api/admin/scrapers/dragon_store",
        json={"times": ["09:00"], "enabled": True},
        headers=_bearer(token),
    )
    session = new_session()
    try:
        for minutes in (2, 4):
            session.add(
                ScrapeRun(
                    scraper_id="dragon_store",
                    trigger="scheduled",
                    started_at=datetime.now(UTC) - timedelta(hours=1),
                    finished_at=datetime.now(UTC) - timedelta(hours=1) + timedelta(minutes=minutes),
                    status="ok",
                )
            )
        session.commit()
    finally:
        session.close()

    day = client.get("/api/admin/scrapers/calendar", headers=_bearer(token)).json()
    assert day["slots"][0]["avg_seconds"] == 180, "the mean of two and four minutes"


def test_a_broken_date_is_a_422(client: TestClient) -> None:
    token = _admin_token(client)
    bad = client.get("/api/admin/scrapers/calendar?date=not-a-date", headers=_bearer(token))
    assert bad.status_code == 422
    assert bad.json()["code"] == "invalid_date"
