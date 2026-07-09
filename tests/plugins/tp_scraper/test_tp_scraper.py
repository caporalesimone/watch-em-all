"""Tests for the TP Scraper fake-product generator (dev QA tool).

The plugin owns a ``products`` table and, on every add/remove/clear, re-delivers
the user's FULL set through the Catalog Update Service: adds appear in the
catalog, removes/clears delist them. It is NOT a scheduled scraper — it does not
implement ``run_for_user`` (so ``implements_scraping`` stays False).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

TP = "/api/plugins/tp-scraper/products"


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


def _catalog_tp_rows() -> list[tuple[str, bool]]:
    """(name, removed) for every tp_scraper catalog row, read straight from the DB."""
    from sqlalchemy import select

    from src.core.db import new_session
    from src.core.models import CatalogProduct

    session = new_session()
    try:
        rows = session.scalars(
            select(CatalogProduct).where(CatalogProduct.plugin_id == "tp_scraper")
        ).all()
        return [(r.name, r.removed) for r in rows]
    finally:
        session.close()


def test_add_generates_named_tp_product_in_catalog(client: TestClient) -> None:
    token = _admin_token(client)
    resp = client.post(TP, json={"currency": "EUR"}, headers=_bearer(token))
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"].startswith("TP - ")
    assert body["currency"] == "EUR"

    rows = _catalog_tp_rows()
    assert len(rows) == 1
    name, removed = rows[0]
    assert name.startswith("TP - ")
    assert removed is False


def test_add_twice_keeps_both(client: TestClient) -> None:
    token = _admin_token(client)
    client.post(TP, json={}, headers=_bearer(token))
    client.post(TP, json={}, headers=_bearer(token))

    listed = client.get(TP, headers=_bearer(token)).json()
    assert len(listed) == 2  # own table accumulates; no delisting between adds

    rows = _catalog_tp_rows()
    assert len(rows) == 2
    assert all(removed is False for _, removed in rows)


def test_remove_delists_in_catalog(client: TestClient) -> None:
    token = _admin_token(client)
    created = client.post(TP, json={}, headers=_bearer(token)).json()

    resp = client.delete(f"{TP}/{created['id']}", headers=_bearer(token))
    assert resp.status_code == 204

    assert client.get(TP, headers=_bearer(token)).json() == []  # gone from own table
    rows = _catalog_tp_rows()
    assert rows and all(removed is True for _, removed in rows)  # delisted, not deleted


def test_clear_all_delists_everything(client: TestClient) -> None:
    token = _admin_token(client)
    client.post(TP, json={}, headers=_bearer(token))
    client.post(TP, json={}, headers=_bearer(token))

    resp = client.delete(TP, headers=_bearer(token))
    assert resp.status_code == 204

    assert client.get(TP, headers=_bearer(token)).json() == []
    rows = _catalog_tp_rows()
    assert len(rows) == 2
    assert all(removed is True for _, removed in rows)


def test_currency_option_is_honored(client: TestClient) -> None:
    token = _admin_token(client)
    resp = client.post(TP, json={"currency": "usd"}, headers=_bearer(token))
    assert resp.status_code == 201
    assert resp.json()["currency"] == "USD"


def test_invalid_currency_rejected(client: TestClient) -> None:
    token = _admin_token(client)
    resp = client.post(TP, json={"currency": "XYZ"}, headers=_bearer(token))
    assert resp.status_code == 422
    assert resp.json()["code"] == "invalid_currency"


def test_tp_scraper_is_not_schedulable(client: TestClient) -> None:
    # It must NOT implement run_for_user, so no scrape-now endpoints are mounted.
    from src.core.scrape import implements_scraping

    app = client.app
    loaded = {lp.plugin.plugin_id: lp for lp in app.state.loaded_plugins}  # type: ignore[attr-defined]
    tp = loaded["tp_scraper"].plugin
    assert implements_scraping(tp) is False
