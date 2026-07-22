"""Tests for the alert-cadence API (phase 6.B7): GET/PUT /api/me/alert-schedule.

Auth-gated, per-user. Turning the cadence off/on drives the baseline (ALERT-R3), and the
PUT response declares the effect. Inputs are validated (bad time / weekday → 422).
"""

from __future__ import annotations

from fastapi.testclient import TestClient


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


def _make_user(client: TestClient, admin_token: str, username: str) -> str:
    client.post(
        "/api/admin/users",
        json={
            "username": username,
            "first_name": "Test",
            "last_name": "User",
            "role": "user",
            "temp_password": "temp-pass-123",
        },
        headers=_bearer(admin_token),
    )
    login = client.post("/api/auth/login", json={"username": username, "password": "temp-pass-123"})
    access = login.json()["access_token"]
    client.post(
        "/api/auth/change-password", json={"new_password": "userpass123"}, headers=_bearer(access)
    )
    relogin = client.post("/api/auth/login", json={"username": username, "password": "userpass123"})
    return str(relogin.json()["access_token"])


def test_requires_auth(client: TestClient) -> None:
    assert client.get("/api/me/alert-schedule").status_code == 401


def test_default_is_off(client: TestClient) -> None:
    token = _make_user(client, _admin_token(client), "alice")
    got = client.get("/api/me/alert-schedule", headers=_bearer(token)).json()
    assert got["weekdays"] == []
    assert got["scheduled_time"] == "09:00:00"


def test_set_and_get(client: TestClient) -> None:
    token = _make_user(client, _admin_token(client), "alice")
    resp = client.put(
        "/api/me/alert-schedule",
        json={"scheduled_time": "8:30", "weekdays": [0, 2, 4]},
        headers=_bearer(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["scheduled_time"] == "08:30:00"  # canonicalised
    assert body["weekdays"] == [0, 2, 4]
    got = client.get("/api/me/alert-schedule", headers=_bearer(token)).json()
    assert got["weekdays"] == [0, 2, 4]


def test_invalid_inputs_rejected(client: TestClient) -> None:
    token = _make_user(client, _admin_token(client), "alice")
    bad_time = client.put(
        "/api/me/alert-schedule",
        json={"scheduled_time": "99:99", "weekdays": [1]},
        headers=_bearer(token),
    )
    assert bad_time.status_code == 422
    assert bad_time.json()["code"] == "invalid_schedule"

    bad_day = client.put(
        "/api/me/alert-schedule",
        json={"scheduled_time": "09:00", "weekdays": [9]},
        headers=_bearer(token),
    )
    assert bad_day.status_code == 422


def test_baseline_effect_on_off_on(client: TestClient) -> None:
    from src.core.db import new_session
    from src.core.models import AlertSnapshot

    token = _make_user(client, _admin_token(client), "alice")
    cart_id = client.post(
        "/api/carts", json={"name": "C", "mode": "cross"}, headers=_bearer(token)
    ).json()["id"]
    # Enabling an alert type seeds the baseline (6.B2).
    client.put(
        f"/api/carts/{cart_id}/alert-types",
        json={"alert_types": ["PRODUCT_ON_SALE"]},
        headers=_bearer(token),
    )

    # Turn the cadence ON: was off → re-seeded.
    on = client.put(
        "/api/me/alert-schedule",
        json={"scheduled_time": "09:00", "weekdays": [0, 1, 2, 3, 4, 5, 6]},
        headers=_bearer(token),
    ).json()
    assert on["baseline_effect"] == "reseeded"
    with new_session() as db:
        assert db.query(AlertSnapshot).filter_by(cart_id=cart_id).one_or_none() is not None

    # Turn it OFF: baselines cleared (no backlog on re-enable, ALERT-R3).
    off = client.put(
        "/api/me/alert-schedule",
        json={"scheduled_time": "09:00", "weekdays": []},
        headers=_bearer(token),
    ).json()
    assert off["baseline_effect"] == "cleared"
    with new_session() as db:
        assert db.query(AlertSnapshot).filter_by(cart_id=cart_id).one_or_none() is None
