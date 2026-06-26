"""Tests for the system log (4.B7): the DB logging handler, the cursor read, retention,
and the admin endpoint."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from src.core.db import new_session
from src.core.maintenance import purge_expired
from src.core.models import ScrapeRun, ScrapeUserLog, SystemLog
from src.core.system_log import distinct_sources, level_counts, list_logs, page_logs


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


def _user_token(client: TestClient, admin: str) -> str:
    client.post(
        "/api/admin/users",
        json={
            "username": "alice",
            "first_name": "Alice",
            "last_name": "Doe",
            "role": "user",
            "temp_password": "temp-pass-123",
        },
        headers=_bearer(admin),
    )
    login = client.post("/api/auth/login", json={"username": "alice", "password": "temp-pass-123"})
    access = login.json()["access_token"]
    client.post(
        "/api/auth/change-password",
        json={"new_password": "alice-pass-123"},
        headers=_bearer(access),
    )
    relogin = client.post(
        "/api/auth/login", json={"username": "alice", "password": "alice-pass-123"}
    )
    return str(relogin.json()["access_token"])


def test_handler_persists_only_worker_and_scraper(client: TestClient) -> None:
    logging.getLogger("wea.worker.test").info("worker-evt")
    logging.getLogger("wea.plugin.demo").warning("scraper-evt")
    logging.getLogger("wea.web.test").info("web-evt")  # not a system source -> skipped
    logging.getLogger("src.something").error("module-evt")  # skipped
    session = new_session()
    try:
        rows = list(session.scalars(select(SystemLog)))
    finally:
        session.close()
    by_msg = {r.message: r for r in rows}
    assert by_msg["worker-evt"].source == "worker"
    assert by_msg["worker-evt"].level == "info"
    assert by_msg["scraper-evt"].source == "scraper"
    assert by_msg["scraper-evt"].level == "warning"
    assert "web-evt" not in by_msg
    assert "module-evt" not in by_msg


def test_list_logs_cursor_and_filters(client: TestClient) -> None:
    session = new_session()
    try:
        for i in range(5):
            session.add(SystemLog(level="info", source="worker", message=f"m{i}"))
        session.add(SystemLog(level="error", source="scraper", message="boom"))
        session.commit()

        rows = list_logs(session, limit=100)
        ids = [r.id for r in rows]
        assert ids == sorted(ids)  # ascending

        cut = rows[1].id
        newer = list_logs(session, since=cut)
        assert newer and all(r.id > cut for r in newer)

        errs = list_logs(session, level="error")
        assert errs and all(r.level == "error" for r in errs)
        scr = list_logs(session, sources=["scraper"])
        assert scr and all(r.source == "scraper" for r in scr)

        last2 = list_logs(session, limit=2)  # most recent N, returned ascending
        assert len(last2) == 2 and last2[0].id < last2[1].id
    finally:
        session.close()


def test_purge_expired_removes_old(client: TestClient) -> None:
    session = new_session()
    try:
        now = datetime.now(UTC)
        old = now - timedelta(days=100)
        session.add(SystemLog(level="info", source="worker", message="old", created_at=old))
        session.add(SystemLog(level="info", source="worker", message="recent"))
        run_old = ScrapeRun(scraper_id="x", trigger="scheduled", started_at=old, status="ok")
        session.add(run_old)
        session.flush()
        session.add(ScrapeUserLog(run_id=run_old.run_id, user_id=1, started_at=old))
        run_new = ScrapeRun(scraper_id="x", trigger="scheduled", started_at=now, status="ok")
        session.add(run_new)
        session.commit()
        old_run_id = run_old.run_id

        counts = purge_expired(session, now, 90)
        assert counts["system_log"] >= 1
        assert counts["scrape_run"] >= 1

        msgs = {r.message for r in session.scalars(select(SystemLog))}
        assert "old" not in msgs and "recent" in msgs
        run_ids = {r.run_id for r in session.scalars(select(ScrapeRun))}
        assert run_new.run_id in run_ids and old_run_id not in run_ids
        assert (
            session.scalar(select(ScrapeUserLog).where(ScrapeUserLog.run_id == old_run_id)) is None
        )
    finally:
        session.close()


def test_purge_disabled_when_retention_zero(client: TestClient) -> None:
    session = new_session()
    try:
        session.add(
            SystemLog(
                level="info",
                source="worker",
                message="keep",
                created_at=datetime.now(UTC) - timedelta(days=999),
            )
        )
        session.commit()
        assert purge_expired(session, datetime.now(UTC), 0) == {"system_log": 0, "scrape_run": 0}
        assert "keep" in {r.message for r in session.scalars(select(SystemLog))}
    finally:
        session.close()


def test_logs_endpoint_admin_only(client: TestClient) -> None:
    assert client.get("/api/admin/logs").status_code == 401
    admin = _admin_token(client)
    user = _user_token(client, admin)
    assert client.get("/api/admin/logs", headers=_bearer(user)).status_code == 403
    resp = client.get("/api/admin/logs", headers=_bearer(admin))
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_logs_endpoint_level_filter(client: TestClient) -> None:
    h = _bearer(_admin_token(client))
    session = new_session()
    try:
        session.add(SystemLog(level="error", source="worker", message="E1"))
        session.commit()
    finally:
        session.close()
    errs = client.get("/api/admin/logs?level=error", headers=h).json()
    assert any(e["message"] == "E1" for e in errs)
    assert all(e["level"] == "error" for e in errs)


def test_list_logs_q_and_multi_source(client: TestClient) -> None:
    session = new_session()
    try:
        session.add(SystemLog(level="info", source="worker", message="uqz alpha one"))
        session.add(SystemLog(level="info", source="scraper", message="uqz beta two"))
        session.add(SystemLog(level="warning", source="scraper", message="uqz alpha three"))
        session.commit()
        hits = list_logs(session, q="UQZ ALPHA")  # ILIKE, case-insensitive substring
        assert {r.message for r in hits} == {"uqz alpha one", "uqz alpha three"}
        scr = list_logs(session, sources=["scraper"], q="uqz")
        assert {r.message for r in scr} == {"uqz beta two", "uqz alpha three"}
        both = list_logs(session, sources=["worker", "scraper"], q="uqz")
        assert len(both) == 3
    finally:
        session.close()


def test_page_logs_counts_and_sources(client: TestClient) -> None:
    session = new_session()
    try:
        for i in range(7):
            session.add(SystemLog(level="info", source="worker", message=f"PGT w{i}"))
        session.add(SystemLog(level="error", source="scraper", message="PGT boom"))
        session.commit()

        page1, total = page_logs(session, page=1, size=5, q="PGT")
        assert total == 8 and len(page1) == 5
        assert page1[0].id > page1[-1].id  # newest first
        page2, total2 = page_logs(session, page=2, size=5, q="PGT")
        assert total2 == 8 and len(page2) == 3
        assert not ({r.id for r in page1} & {r.id for r in page2})  # no overlap

        # counts respect the source/search filters but not the level filter
        assert level_counts(session, q="PGT") == {"info": 7, "warning": 0, "error": 1}
        assert level_counts(session, sources=["scraper"], q="PGT") == {
            "info": 0,
            "warning": 0,
            "error": 1,
        }
        assert "scraper" in distinct_sources(session) and "worker" in distinct_sources(session)
    finally:
        session.close()


def test_logs_page_endpoint(client: TestClient) -> None:
    assert client.get("/api/admin/logs/page").status_code == 401
    h = _bearer(_admin_token(client))
    session = new_session()
    try:
        session.add(SystemLog(level="error", source="scraper", message="kaboom"))
        session.add(SystemLog(level="info", source="worker", message="ok tick"))
        session.commit()
    finally:
        session.close()
    body = client.get("/api/admin/logs/page?size=10", headers=h).json()
    assert set(body) == {"items", "total", "counts", "sources"}
    assert body["total"] >= 2
    assert "scraper" in body["sources"] and "worker" in body["sources"]
    only = client.get("/api/admin/logs/page?q=kaboom", headers=h).json()
    assert only["total"] == 1 and only["items"][0]["message"] == "kaboom"
