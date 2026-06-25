"""Tests for admin scraper scheduling (4.B2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from src.core.db import new_session
from src.core.models import ScrapeCache as ScrapeCacheRow
from src.core.scrape_cache import cache_key


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _admin_token(client: TestClient) -> str:
    login = client.post("/api/auth/login", json={"username": "admin", "password": "initpass123"})
    access = login.json()["access_token"]
    client.post(
        "/api/auth/change-password",
        json={"new_password": "adminpass123"},
        headers=_bearer(access),
    )
    relogin = client.post("/api/auth/login", json={"username": "admin", "password": "adminpass123"})
    return str(relogin.json()["access_token"])


def test_scrapers_requires_admin(client: TestClient) -> None:
    assert client.get("/api/admin/scrapers").status_code == 401


def test_lists_schedulable_scrapers_and_sets_slots(client: TestClient) -> None:
    h = _bearer(_admin_token(client))
    listed = client.get("/api/admin/scrapers", headers=h).json()
    by_id = {s["scraper_id"]: s for s in listed}
    # Dragon Store scrapes (implements run_for_user); tp_scraper does not → excluded.
    assert "dragon_store" in by_id
    assert "tp_scraper" not in by_id
    assert by_id["dragon_store"]["times"] == []
    assert by_id["dragon_store"]["enabled"] is True

    put = client.put(
        "/api/admin/scrapers/dragon_store",
        json={"times": ["22:00", "06:00", "06:00"], "enabled": False},
        headers=h,
    )
    assert put.status_code == 200
    # De-duplicated and sorted.
    assert put.json()["times"] == ["06:00", "22:00"]
    assert put.json()["enabled"] is False

    again = {s["scraper_id"]: s for s in client.get("/api/admin/scrapers", headers=h).json()}
    assert again["dragon_store"]["times"] == ["06:00", "22:00"]


def test_rejects_unknown_scraper_and_bad_time(client: TestClient) -> None:
    h = _bearer(_admin_token(client))
    assert (
        client.put("/api/admin/scrapers/nope", json={"times": [], "enabled": True}, headers=h)
    ).status_code == 404
    assert (
        client.put(
            "/api/admin/scrapers/dragon_store",
            json={"times": ["25:00"], "enabled": True},
            headers=h,
        )
    ).status_code == 422


def _seed_cache(plugin_id: str, paths: list[str]) -> None:
    session = new_session()
    try:
        for p in paths:
            session.add(
                ScrapeCacheRow(
                    plugin_id=plugin_id,
                    cache_key=cache_key(plugin_id, "GET", f"http://h/{p}"),
                    response_body=b"x",
                    response_meta_json={"status": 200, "content_type": "text/html"},
                    fetched_at=datetime.now(UTC),
                    expires_at=datetime.now(UTC) + timedelta(minutes=30),
                )
            )
        session.commit()
    finally:
        session.close()


def test_clear_cache_admin_only_unknown_404_and_counts(client: TestClient) -> None:
    assert client.delete("/api/admin/scrapers/dragon_store/cache").status_code == 401
    h = _bearer(_admin_token(client))
    assert client.delete("/api/admin/scrapers/nope/cache", headers=h).status_code == 404

    _seed_cache("dragon_store", ["a", "b"])
    resp = client.delete("/api/admin/scrapers/dragon_store/cache", headers=h)
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 2
    # A second clear removes nothing.
    assert client.delete("/api/admin/scrapers/dragon_store/cache", headers=h).json()["deleted"] == 0
