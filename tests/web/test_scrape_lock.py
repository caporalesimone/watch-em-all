"""Scrape-now refuses (409) when a run already holds the per-scraper lock (4.B5)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.core.db import get_engine
from src.core.locks import acquire_scraper_lock

DS = "/api/plugins/dragon-store"


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
            "username": "carol",
            "first_name": "Carol",
            "last_name": "Doe",
            "role": "user",
            "temp_password": "temp-pass-123",
        },
        headers=_bearer(admin),
    )
    login = client.post("/api/auth/login", json={"username": "carol", "password": "temp-pass-123"})
    access = login.json()["access_token"]
    client.post(
        "/api/auth/change-password",
        json={"new_password": "carol-pass-123"},
        headers=_bearer(access),
    )
    relogin = client.post(
        "/api/auth/login", json={"username": "carol", "password": "carol-pass-123"}
    )
    return str(relogin.json()["access_token"])


def test_scrape_now_409_when_a_run_holds_the_lock(client: TestClient) -> None:
    token = _user_token(client, _admin_token(client))
    lock = acquire_scraper_lock(get_engine(), "dragon_store")
    assert lock is not None
    try:
        resp = client.post(f"{DS}/scrape-now", headers=_bearer(token))
        assert resp.status_code == 409
        assert resp.json()["code"] == "scrape_in_progress"
    finally:
        lock.release()
