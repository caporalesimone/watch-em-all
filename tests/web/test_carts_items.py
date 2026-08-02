"""Tests for cart membership rules (phase 5.B2).

Add/remove catalog products as cart members, with the batch rules: products must
be the user's catalog rows (CART-R1), not delisted (out-of-stock is fine), of the
cart's scraper for scraper_specific (CART-R4), and a single currency per cart. Add
is idempotent; remove of a non-member is a no-op.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

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


def _make_user(client: TestClient, admin_token: str, username: str) -> tuple[int, str]:
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
        "/api/auth/change-password", json={"new_password": "userpass123"}, headers=_bearer(access)
    )
    relogin = client.post("/api/auth/login", json={"username": username, "password": "userpass123"})
    return uid, str(relogin.json()["access_token"])


def _seed(user_id: int, plugin_id: str, *products: dict[str, object]) -> None:
    from src.core.catalog import update_catalog
    from src.core.contracts import Product
    from src.core.db import new_session

    items = []
    for over in products:
        base: dict[str, object] = {
            "plugin_id": plugin_id,
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
        update_catalog(session, user_id, plugin_id, items)
    finally:
        session.close()


def _ids_by_external(client: TestClient, token: str) -> dict[str, int]:
    body = client.get("/api/catalog?page_size=100", headers=_bearer(token)).json()
    return {i["external_id"]: int(i["id"]) for i in body["items"]}


def _set_removed(product_id: int) -> None:
    from src.core.db import new_session
    from src.core.models import CatalogProduct

    session = new_session()
    try:
        product = session.get(CatalogProduct, product_id)
        assert product is not None
        product.removed = True
        session.commit()
    finally:
        session.close()


def _add(client: TestClient, token: str, cart_id: int, ids: list[int]):  # type: ignore[no-untyped-def]
    return client.post(
        f"/api/carts/{cart_id}/items", json={"product_ids": ids}, headers=_bearer(token)
    )


def _remove(client: TestClient, token: str, cart_id: int, ids: list[int]):  # type: ignore[no-untyped-def]
    return client.request(
        "DELETE", f"/api/carts/{cart_id}/items", json={"product_ids": ids}, headers=_bearer(token)
    )


def _cross_cart(client: TestClient, token: str) -> int:
    return int(
        client.post(
            "/api/carts", json={"name": "C", "mode": "cross"}, headers=_bearer(token)
        ).json()["id"]
    )


def test_add_remove_and_idempotency(client: TestClient) -> None:
    uid, token = _make_user(client, _admin_token(client), "alice@example.com")
    _seed(uid, "dragon_store", {"external_id": "a"}, {"external_id": "b"})
    ids = _ids_by_external(client, token)
    cart = _cross_cart(client, token)

    assert _add(client, token, cart, [ids["a"], ids["b"]]).json()["member_count"] == 2
    # adding "a" again is idempotent
    assert _add(client, token, cart, [ids["a"]]).json()["member_count"] == 2
    # remove "a"
    assert _remove(client, token, cart, [ids["a"]]).json()["member_count"] == 1
    # removing a non-member is a no-op
    assert _remove(client, token, cart, [ids["a"]]).json()["member_count"] == 1


def test_cannot_add_delisted_but_can_add_out_of_stock(client: TestClient) -> None:
    uid, token = _make_user(client, _admin_token(client), "alice@example.com")
    _seed(
        uid,
        "dragon_store",
        {"external_id": "gone"},
        {"external_id": "oos", "is_available": False},  # out of stock, still listed
    )
    ids = _ids_by_external(client, token)
    _set_removed(ids["gone"])
    cart = _cross_cart(client, token)

    delisted = _add(client, token, cart, [ids["gone"]])
    assert delisted.status_code == 422
    assert delisted.json()["code"] == "product_delisted"

    oos = _add(client, token, cart, [ids["oos"]])
    assert oos.status_code == 200
    assert oos.json()["member_count"] == 1


def test_scraper_specific_rejects_foreign_scraper_product(client: TestClient) -> None:
    uid, token = _make_user(client, _admin_token(client), "alice@example.com")
    _seed(uid, "dragon_store", {"external_id": "d"})
    _seed(uid, "other_shop", {"external_id": "o"})
    ids = _ids_by_external(client, token)
    cart = int(
        client.post(
            "/api/carts",
            json={"name": "W", "mode": "scraper_specific", "scraper_id": "dragon_store"},
            headers=_bearer(token),
        ).json()["id"]
    )

    wrong = _add(client, token, cart, [ids["o"]])
    assert wrong.status_code == 422
    assert wrong.json()["code"] == "product_scraper_mismatch"
    assert _add(client, token, cart, [ids["d"]]).json()["member_count"] == 1


def test_single_currency_per_cart(client: TestClient) -> None:
    uid, token = _make_user(client, _admin_token(client), "alice@example.com")
    _seed(
        uid,
        "dragon_store",
        {"external_id": "eur", "currency": "EUR"},
        {"external_id": "usd", "currency": "USD"},
    )
    ids = _ids_by_external(client, token)
    cart = _cross_cart(client, token)

    assert _add(client, token, cart, [ids["eur"]]).json()["member_count"] == 1
    mismatch = _add(client, token, cart, [ids["usd"]])
    assert mismatch.status_code == 422
    assert mismatch.json()["code"] == "currency_mismatch"


def test_add_rejects_foreign_catalog_id(client: TestClient) -> None:
    _uid, token = _make_user(client, _admin_token(client), "alice@example.com")
    cart = _cross_cart(client, token)
    resp = _add(client, token, cart, [999999])
    assert resp.status_code == 422
    assert resp.json()["code"] == "product_not_found"


def test_scraper_specific_cart_shows_dragon_adjustments(client: TestClient) -> None:
    uid, token = _make_user(client, _admin_token(client), "alice@example.com")
    _seed(
        uid,
        "dragon_store",
        {
            "external_id": "p1",
            "price_current": Decimal("150.00"),
            "price_original": Decimal("150.00"),
        },
        {
            "external_id": "p2",
            "price_current": Decimal("100.00"),
            "price_original": Decimal("100.00"),
        },
    )
    ids = _ids_by_external(client, token)
    cart = int(
        client.post(
            "/api/carts",
            json={"name": "Wishlist", "mode": "scraper_specific", "scraper_id": "dragon_store"},
            headers=_bearer(token),
        ).json()["id"]
    )
    detail = _add(client, token, cart, [ids["p1"], ids["p2"]]).json()  # discounted total 250

    assert Decimal(detail["total_discounted"]) == Decimal("250.00")
    by_id = {a["id"]: Decimal(a["amount"]) for a in detail["adjustments"]}
    assert by_id["dragon_store.adjustments.threshold_discount"] == Decimal("25.00")  # 10%
    assert by_id["dragon_store.adjustments.free_shipping"] == Decimal("0.00")
    # final = 250 − (25 + 0) = 225
    assert Decimal(detail["final_price"]) == Decimal("225.00")


def test_threshold_set_clear_and_validation(client: TestClient) -> None:
    uid, token = _make_user(client, _admin_token(client), "alice@example.com")
    _seed(uid, "dragon_store", {"external_id": "a"})  # price 10.00, active
    ids = _ids_by_external(client, token)
    cart = _cross_cart(client, token)
    _add(client, token, cart, [ids["a"]])

    reached = client.patch(
        f"/api/carts/{cart}", json={"threshold_amount": "10.00"}, headers=_bearer(token)
    ).json()
    assert reached["threshold"]["reached"] is True
    assert reached["threshold"]["partial"] is False

    tighter = client.patch(
        f"/api/carts/{cart}", json={"threshold_amount": "5.00"}, headers=_bearer(token)
    ).json()
    assert tighter["threshold"]["reached"] is False

    cleared = client.patch(
        f"/api/carts/{cart}", json={"threshold_amount": None}, headers=_bearer(token)
    ).json()
    assert cleared["threshold"] is None

    bad = client.patch(
        f"/api/carts/{cart}", json={"threshold_amount": "-1"}, headers=_bearer(token)
    )
    assert bad.status_code == 422
    assert bad.json()["code"] == "threshold_must_be_positive"
