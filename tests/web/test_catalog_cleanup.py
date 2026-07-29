"""Catalog cleanups and the super-user level (9.B7 / 9.B8).

The three cleanups answer three different intentions — tidy up what the site no longer offers,
drop this one, start over — and each has to say how many rows went, because "nothing was
delisted" and "twelve products went" are different answers to the same click.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from src.core.catalog import update_catalog
from src.core.contracts import Product
from src.core.db import new_session
from src.core.models import CartMember, CatalogProduct, PriceHistory

PLUGIN = "dragon_store"


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _admin_token(client: TestClient) -> str:
    """Idempotent: the first call changes the forced initial password, later ones just log in.
    Without that, the second account a test creates fails at login with a KeyError instead of
    saying what went wrong."""
    for password in ("adminpass123", "initpass123"):
        login = client.post("/api/auth/login", json={"username": "admin", "password": password})
        if login.status_code != 200:
            continue
        token = str(login.json()["access_token"])
        if password == "initpass123":
            client.post(
                "/api/auth/change-password",
                json={"new_password": "adminpass123"},
                headers=_bearer(token),
            )
            again = client.post(
                "/api/auth/login", json={"username": "admin", "password": "adminpass123"}
            )
            return str(again.json()["access_token"])
        return token
    raise AssertionError("could not authenticate as admin")


def _account(client: TestClient, username: str, role: str = "user") -> tuple[int, str]:
    admin = _admin_token(client)
    created = client.post(
        "/api/admin/users",
        json={
            "username": username,
            "first_name": "T",
            "last_name": "U",
            "role": role,
            "temp_password": "temp-pass-123",
        },
        headers=_bearer(admin),
    )
    uid = int(created.json()["id"])
    login = client.post("/api/auth/login", json={"username": username, "password": "temp-pass-123"})
    access = login.json()["access_token"]
    client.post(
        "/api/auth/change-password", json={"new_password": "userpass123"}, headers=_bearer(access)
    )
    relogin = client.post("/api/auth/login", json={"username": username, "password": "userpass123"})
    return uid, str(relogin.json()["access_token"])


def _product(external_id: str, name: str) -> Product:
    from datetime import UTC, datetime

    return Product(
        plugin_id=PLUGIN,
        external_id=external_id,
        url=f"https://x/p.1.1.1.gp.{external_id}.uw",
        name=name,
        price_current=Decimal("10.00"),
        price_original=Decimal("10.00"),
        discount_pct=None,
        currency="EUR",
        is_available=True,
        scraped_at=datetime.now(UTC),
        extra={},
    )


def _seed(uid: int, *externals: str) -> None:
    session = new_session()
    try:
        update_catalog(session, uid, PLUGIN, [_product(e, f"Product {e}") for e in externals])
    finally:
        session.close()


def _delist(uid: int, keep: str) -> None:
    """A complete delivery that only offers `keep`: everything else becomes delisted."""
    session = new_session()
    try:
        update_catalog(session, uid, PLUGIN, [_product(keep, f"Product {keep}")])
    finally:
        session.close()


def test_removing_delisted_products_leaves_the_live_ones(client: TestClient) -> None:
    uid, token = _account(client, "alice")
    h = _bearer(token)
    _seed(uid, "a", "b", "c")
    _delist(uid, "a")

    removed = client.delete("/api/catalog/delisted", headers=h)
    assert removed.status_code == 200
    assert removed.json()["removed"] == 2
    page = client.get("/api/catalog", headers=h).json()
    assert page["total"] == 1
    assert page["items"][0]["external_id"] == "a"


def test_removing_delisted_when_there_are_none_says_zero(client: TestClient) -> None:
    """A count, not a bare 204: the page has to be able to say "there was nothing to tidy"."""
    uid, token = _account(client, "alice")
    _seed(uid, "a")
    assert client.delete("/api/catalog/delisted", headers=_bearer(token)).json()["removed"] == 0


def test_removing_one_product_takes_its_history_and_cart_membership_with_it(
    client: TestClient,
) -> None:
    """The cascade is the whole reason these endpoints have to be honest about what they do:
    price_history and cart_members hang off products with ON DELETE CASCADE."""
    uid, token = _account(client, "alice")
    h = _bearer(token)
    _seed(uid, "a", "b")
    product_id = client.get("/api/catalog", headers=h).json()["items"][0]["id"]
    cart = client.post("/api/carts", json={"name": "C", "mode": "cross"}, headers=h).json()
    client.post(f"/api/carts/{cart['id']}/items", json={"product_ids": [product_id]}, headers=h)

    session = new_session()
    try:
        assert session.scalar(select(func.count()).select_from(CartMember)) == 1
        assert session.scalar(select(func.count()).select_from(PriceHistory)) == 2
    finally:
        session.close()

    assert client.delete(f"/api/catalog/{product_id}", headers=h).json()["removed"] == 1

    session = new_session()
    try:
        assert session.scalar(select(func.count()).select_from(CatalogProduct)) == 1
        assert session.scalar(select(func.count()).select_from(CartMember)) == 0
        assert session.scalar(select(func.count()).select_from(PriceHistory)) == 1
    finally:
        session.close()


def test_someone_elses_product_reads_as_not_found(client: TestClient) -> None:
    """Never 403: that would confirm the row exists."""
    uid_a, _ = _account(client, "alice")
    _uid_b, token_b = _account(client, "bob")
    _seed(uid_a, "a")
    session = new_session()
    try:
        product_id = session.scalars(select(CatalogProduct)).one().id
    finally:
        session.close()

    refused = client.delete(f"/api/catalog/{product_id}", headers=_bearer(token_b))
    assert refused.status_code == 404
    assert refused.json()["code"] == "not_found"


def test_emptying_the_catalog_removes_everything_of_that_user_only(client: TestClient) -> None:
    uid_a, token_a = _account(client, "alice")
    uid_b, token_b = _account(client, "bob")
    _seed(uid_a, "a", "b", "c")
    _seed(uid_b, "d")

    assert client.delete("/api/catalog", headers=_bearer(token_a)).json()["removed"] == 3
    assert client.get("/api/catalog", headers=_bearer(token_a)).json()["total"] == 0
    assert client.get("/api/catalog", headers=_bearer(token_b)).json()["total"] == 1


def test_a_plain_user_cannot_reach_the_manual_scrape(client: TestClient) -> None:
    """9.B8: the manual scrape is the quickest way to send a site requests its Crawl-delay never
    asked for, so it belongs to the super-user. Refused by the API, not by a hidden button."""
    _uid, token = _account(client, "alice")
    h = _bearer(token)
    assert client.post("/api/plugins/dragon-store/scrape-now", headers=h).status_code == 403
    assert client.get("/api/plugins/dragon-store/scrape-now", headers=h).status_code == 403


def test_a_super_user_and_an_admin_can(client: TestClient) -> None:
    _uid, token = _account(client, "sudo", role="super_user")
    assert (
        client.get("/api/plugins/dragon-store/scrape-now", headers=_bearer(token)).status_code
        == 200
    )
    admin = _admin_token(client)
    assert (
        client.get("/api/plugins/dragon-store/scrape-now", headers=_bearer(admin)).status_code
        == 200
    )
