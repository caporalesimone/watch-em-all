"""Tests for the alert history API (phase 6.B8): list, detail, mark-read, unread-count.

Auth-gated and per-user. Rows are inserted directly (the engine that produces them is
tested elsewhere); here we check the read side, pagination, kind filter and read state.
"""

from __future__ import annotations

from datetime import UTC, datetime

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
            "first_name": "T",
            "last_name": "U",
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


def _uid(client: TestClient, token: str) -> int:
    return int(client.get("/api/me", headers=_bearer(token)).json()["id"])


def _seed_alert(user_id: int, cart_count: int = 1) -> int:
    from src.core.db import new_session
    from src.core.models import AlertLog

    payload = {
        "kind": "alert_digest",
        "user_id": user_id,
        "generated_at": "2026-07-22T09:00:00+00:00",
        "cart_alerts": [{"cart_id": i, "cart_name": f"Cart {i}"} for i in range(cart_count)],
    }
    with new_session() as db:
        row = AlertLog(
            user_id=user_id, kind="alert_digest", payload_json=payload, created_at=datetime.now(UTC)
        )
        db.add(row)
        db.commit()
        return int(row.id)


def test_requires_auth(client: TestClient) -> None:
    assert client.get("/api/alerts").status_code == 401
    assert client.get("/api/alerts/unread-count").status_code == 401


def test_list_detail_and_read_flow(client: TestClient) -> None:
    token = _make_user(client, _admin_token(client), "alice@example.com")
    uid = _uid(client, token)
    alert_id = _seed_alert(uid, cart_count=2)

    listed = client.get("/api/alerts", headers=_bearer(token)).json()
    assert listed["total"] == 1
    item = listed["items"][0]
    assert item["id"] == alert_id
    assert item["kind"] == "alert_digest"
    assert item["read"] is False
    assert item["cart_count"] == 2

    # Unread count reflects it.
    assert client.get("/api/alerts/unread-count", headers=_bearer(token)).json()["count"] == 1

    # Detail carries the full payload.
    detail = client.get(f"/api/alerts/{alert_id}", headers=_bearer(token)).json()
    assert detail["payload"]["cart_alerts"][0]["cart_name"] == "Cart 0"
    assert detail["deliveries"] == []

    # Mark read → unread count drops, read flag flips.
    assert client.post(f"/api/alerts/{alert_id}/read", headers=_bearer(token)).status_code == 204
    assert client.get("/api/alerts/unread-count", headers=_bearer(token)).json()["count"] == 0
    assert client.get(f"/api/alerts/{alert_id}", headers=_bearer(token)).json()["read"] is True


def test_kind_filter_and_pagination(client: TestClient) -> None:
    token = _make_user(client, _admin_token(client), "alice@example.com")
    uid = _uid(client, token)
    for _ in range(3):
        _seed_alert(uid)

    page1 = client.get("/api/alerts?page=1&page_size=2", headers=_bearer(token)).json()
    assert page1["total"] == 3
    assert len(page1["items"]) == 2

    none = client.get("/api/alerts?kind=summary", headers=_bearer(token)).json()
    assert none["total"] == 0


def test_alerts_are_per_user(client: TestClient) -> None:
    admin = _admin_token(client)
    token_a = _make_user(client, admin, "alice@example.com")
    token_b = _make_user(client, admin, "bob@example.com")
    alert_id = _seed_alert(_uid(client, token_a))

    assert client.get("/api/alerts", headers=_bearer(token_b)).json()["total"] == 0
    assert client.get(f"/api/alerts/{alert_id}", headers=_bearer(token_b)).status_code == 404
    assert client.post(f"/api/alerts/{alert_id}/read", headers=_bearer(token_b)).status_code == 404


def test_bulk_delete(client: TestClient) -> None:
    token = _make_user(client, _admin_token(client), "alice@example.com")
    uid = _uid(client, token)
    a1, a2, a3 = _seed_alert(uid), _seed_alert(uid), _seed_alert(uid)

    resp = client.request("DELETE", "/api/alerts", json={"ids": [a1, a3]}, headers=_bearer(token))
    assert resp.status_code == 204
    listed = client.get("/api/alerts", headers=_bearer(token)).json()
    assert listed["total"] == 1
    assert listed["items"][0]["id"] == a2


def test_delete_is_per_user(client: TestClient) -> None:
    admin = _admin_token(client)
    token_a = _make_user(client, admin, "alice@example.com")
    token_b = _make_user(client, admin, "bob@example.com")
    alert_id = _seed_alert(_uid(client, token_a))

    # Bob can't delete Alice's alert — the id simply isn't matched (idempotent 204).
    resp = client.request(
        "DELETE", "/api/alerts", json={"ids": [alert_id]}, headers=_bearer(token_b)
    )
    assert resp.status_code == 204
    assert client.get("/api/alerts", headers=_bearer(token_a)).json()["total"] == 1
