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
    # De-duplicated, sorted, canonical HH:MM:SS (4.F1).
    assert put.json()["times"] == ["06:00:00", "22:00:00"]
    assert put.json()["enabled"] is False

    again = {s["scraper_id"]: s for s in client.get("/api/admin/scrapers", headers=h).json()}
    assert again["dragon_store"]["times"] == ["06:00:00", "22:00:00"]


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


def test_list_reports_cache_entries(client: TestClient) -> None:
    h = _bearer(_admin_token(client))
    by_id = {s["scraper_id"]: s for s in client.get("/api/admin/scrapers", headers=h).json()}
    assert by_id["dragon_store"]["cache_entries"] == 0
    _seed_cache("dragon_store", ["a", "b", "c"])
    by_id = {s["scraper_id"]: s for s in client.get("/api/admin/scrapers", headers=h).json()}
    assert by_id["dragon_store"]["cache_entries"] == 3


# --- reserved config (4.B10) ---

CFG = "/api/admin/scrapers/dragon_store/config"


def test_config_requires_admin(client: TestClient) -> None:
    assert client.get(CFG).status_code == 401
    assert client.patch(CFG, json={"http_timeout_s": 20}).status_code == 401


def test_config_get_defaults_then_patch_subset(client: TestClient) -> None:
    h = _bearer(_admin_token(client))
    # Defaults mirror the module constants: 11 s between requests (just above the slowest
    # Crawl-delay we have met) and a 12-hour cache half-life.
    assert client.get(CFG, headers=h).json() == {
        "politeness_delay_ms": 11000,
        "http_timeout_s": 15.0,
        "cache_ttl_min": 720,
        "scrape_now_min_interval_s": 3600,
    }
    patched = client.patch(CFG, json={"cache_ttl_min": 0, "http_timeout_s": 20}, headers=h)
    assert patched.status_code == 200
    body = patched.json()
    assert body["cache_ttl_min"] == 0  # 0 disables the cache
    assert body["http_timeout_s"] == 20.0
    # Untouched keys keep their defaults.
    assert body["politeness_delay_ms"] == 11000
    assert body["scrape_now_min_interval_s"] == 3600
    # Persisted across reads.
    assert client.get(CFG, headers=h).json()["cache_ttl_min"] == 0


def test_config_unknown_scraper_404(client: TestClient) -> None:
    h = _bearer(_admin_token(client))
    assert client.get("/api/admin/scrapers/nope/config", headers=h).status_code == 404
    assert (
        client.patch("/api/admin/scrapers/nope/config", json={"cache_ttl_min": 5}, headers=h)
    ).status_code == 404


def test_config_rejects_unknown_key_and_out_of_range(client: TestClient) -> None:
    h = _bearer(_admin_token(client))
    # Unknown key (extra=forbid) → 422 at the schema boundary.
    assert client.patch(CFG, json={"nope": 1}, headers=h).status_code == 422
    # Out-of-range → 422 from the service validation.
    assert client.patch(CFG, json={"http_timeout_s": 999}, headers=h).status_code == 422
    assert client.patch(CFG, json={"cache_ttl_min": -1}, headers=h).status_code == 422
