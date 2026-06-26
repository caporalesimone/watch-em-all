"""Tests for the catalog read API (GET /api/catalog).

Auth-gated, per-user (DB-R1). Catalog rows are seeded directly through the
Catalog Update Service on the app's engine (no scraper exists yet in this PR).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient

PLUGIN = "dragon_store"


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


def _make_user(client: TestClient, admin_token: str, username: str) -> tuple[int, str]:
    """Create a user, clear the forced password change, return (id, access token)."""
    resp = client.post(
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
    uid = int(resp.json()["id"])
    login = client.post("/api/auth/login", json={"username": username, "password": "temp-pass-123"})
    access = login.json()["access_token"]
    client.post(
        "/api/auth/change-password",
        json={"new_password": "userpass123"},
        headers=_bearer(access),
    )
    relogin = client.post("/api/auth/login", json={"username": username, "password": "userpass123"})
    return uid, str(relogin.json()["access_token"])


def _seed(user_id: int, *products: dict[str, object]) -> None:
    from src.core.catalog import update_catalog
    from src.core.contracts import Product
    from src.core.db import new_session

    items = []
    for over in products:
        base: dict[str, object] = {
            "plugin_id": PLUGIN,
            "external_id": "x",
            "url": "https://example.com/p.gp.1.uw",
            "name": "Item",
            "image_url": None,
            "price_current": Decimal("10.00"),
            "price_original": Decimal("10.00"),
            "discount_pct": None,
            "currency": "EUR",
            "is_available": True,
            "scraped_at": datetime.now(UTC),
            "extra": {},
        }
        base.update(over)
        items.append(Product(**base))  # type: ignore[arg-type]
    session = new_session()
    try:
        update_catalog(session, user_id, PLUGIN, items)
    finally:
        session.close()


def test_catalog_requires_auth(client: TestClient) -> None:
    assert client.get("/api/catalog").status_code == 401


def test_lists_user_catalog(client: TestClient) -> None:
    admin = _admin_token(client)
    uid, token = _make_user(client, admin, "alice")
    _seed(
        uid,
        {"external_id": "a", "name": "Necronomicon", "price_current": Decimal("40.00")},
        {"external_id": "b", "name": "Dice set", "price_current": Decimal("12.50")},
    )
    body = client.get("/api/catalog", headers=_bearer(token)).json()
    assert body["total"] == 2
    assert {i["name"] for i in body["items"]} == {"Necronomicon", "Dice set"}
    # Money is serialised as an exact string; compare by value, not formatting.
    prices = {i["name"]: Decimal(i["price_current"]) for i in body["items"]}
    assert prices["Necronomicon"] == Decimal("40.00")


def test_catalog_is_per_user(client: TestClient) -> None:
    admin = _admin_token(client)
    uid_a, _ = _make_user(client, admin, "alice")
    _, token_b = _make_user(client, admin, "bob")
    _seed(uid_a, {"external_id": "a", "name": "Alice item"})
    body = client.get("/api/catalog", headers=_bearer(token_b)).json()
    assert body["total"] == 0


def test_filter_by_availability(client: TestClient) -> None:
    admin = _admin_token(client)
    uid, token = _make_user(client, admin, "alice")
    _seed(
        uid,
        {"external_id": "a", "name": "In stock", "is_available": True},
        {"external_id": "b", "name": "Sold out", "is_available": False},
    )
    body = client.get("/api/catalog?available=false", headers=_bearer(token)).json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "Sold out"


def test_sort_by_price(client: TestClient) -> None:
    admin = _admin_token(client)
    uid, token = _make_user(client, admin, "alice")
    _seed(
        uid,
        {"external_id": "a", "name": "Cheap", "price_current": Decimal("5.00")},
        {"external_id": "b", "name": "Dear", "price_current": Decimal("99.00")},
    )
    body = client.get("/api/catalog?sort=price_current&order=asc", headers=_bearer(token)).json()
    assert [i["name"] for i in body["items"]] == ["Cheap", "Dear"]


def test_sort_by_list_price(client: TestClient) -> None:
    admin = _admin_token(client)
    uid, token = _make_user(client, admin, "alice")
    _seed(
        uid,
        {"external_id": "a", "name": "Low list", "price_original": Decimal("20.00")},
        {"external_id": "b", "name": "High list", "price_original": Decimal("80.00")},
    )
    body = client.get("/api/catalog?sort=price_original&order=desc", headers=_bearer(token)).json()
    assert [i["name"] for i in body["items"]] == ["High list", "Low list"]


def test_sort_by_availability(client: TestClient) -> None:
    admin = _admin_token(client)
    uid, token = _make_user(client, admin, "alice")
    _seed(
        uid,
        {"external_id": "a", "name": "Available", "is_available": True},
        {"external_id": "b", "name": "Sold out", "is_available": False},
    )
    body = client.get("/api/catalog?sort=is_available&order=asc", headers=_bearer(token)).json()
    assert body["items"][0]["name"] == "Sold out"  # False sorts before True (asc)


def test_pagination(client: TestClient) -> None:
    admin = _admin_token(client)
    uid, token = _make_user(client, admin, "alice")
    _seed(
        uid,
        {"external_id": "a", "name": "One"},
        {"external_id": "b", "name": "Two"},
        {"external_id": "c", "name": "Three"},
    )
    page1 = client.get("/api/catalog?page=1&page_size=2", headers=_bearer(token)).json()
    assert page1["total"] == 3
    assert len(page1["items"]) == 2
    page2 = client.get("/api/catalog?page=2&page_size=2", headers=_bearer(token)).json()
    assert len(page2["items"]) == 1
