"""Tests for admin scraper scheduling (4.B2)."""

from __future__ import annotations

from fastapi.testclient import TestClient


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
