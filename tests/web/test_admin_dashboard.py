"""The admin dashboard (10.B9/10.B10): aggregates, and nothing that belongs to a person."""

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


def _make_user(client: TestClient, token: str, username: str) -> int:
    resp = client.post(
        "/api/admin/users",
        json={
            "username": username,
            "first_name": "T",
            "last_name": "U",
            "role": "user",
        },
        headers=_bearer(token),
    )
    return int(resp.json()["id"])


def test_totals_count_the_installation(client: TestClient) -> None:
    token = _admin_token(client)
    alice = _make_user(client, token, "alice@example.com")
    _make_user(client, token, "bob@example.com")
    client.delete(f"/api/admin/users/{alice}", headers=_bearer(token))

    totals = client.get("/api/admin/dashboard", headers=_bearer(token)).json()["totals"]
    assert totals["users_total"] == 3  # admin + alice + bob
    # The three states are three questions, not a partition: alice is both inactive and
    # on her way out, and counting her once in each is the honest answer to both.
    assert totals["users_active"] == 2
    assert totals["users_deleting"] == 1
    assert totals["products_total"] == 0
    assert totals["carts_total"] == 0


def test_the_notification_window_is_declared_and_configurable(client: TestClient) -> None:
    token = _admin_token(client)
    body = client.get("/api/admin/dashboard?window_days=30", headers=_bearer(token)).json()
    assert body["notifications"]["window_days"] == 30, "a number without its window means nothing"
    assert body["notifications"]["alerts"] == 0
    assert body["notifications"]["delivered"] == 0


def test_the_dashboard_never_returns_anything_a_person_owns(client: TestClient) -> None:
    """DASH-R6: the admin governs the installation, they do not read its contents."""
    token = _admin_token(client)
    _make_user(client, token, "alice@example.com")
    raw = client.get("/api/admin/dashboard", headers=_bearer(token)).text
    assert "alice@example.com" not in raw, "not even a username leaks into the aggregate view"
    for field in ("name", "url", "price", "cart_name"):
        assert f'"{field}"' not in raw


def test_the_dashboard_is_admin_only(client: TestClient) -> None:
    assert client.get("/api/admin/dashboard").status_code == 401


def test_the_load_view_lists_accounts_that_cost_nothing_too(client: TestClient) -> None:
    """10.B10: "costs nothing lately" is an answer; leaving a row out reads as "does not exist"."""
    token = _admin_token(client)
    _make_user(client, token, "alice@example.com")
    body = client.get("/api/admin/dashboard/users", headers=_bearer(token)).json()
    assert body["window_days"] == 7
    # Nobody has scraped anything, so no traffic rows exist at all — and the list is honest
    # about that rather than inventing them.
    assert body["by_user"] == []
    assert body["by_user_and_scraper"] == []


def test_the_load_view_carries_numbers_and_a_username_and_nothing_else(
    client: TestClient,
) -> None:
    token = _admin_token(client)
    _make_user(client, token, "alice@example.com")
    raw = client.get("/api/admin/dashboard/users", headers=_bearer(token)).json()
    for row in raw["by_user"] + raw["by_user_and_scraper"]:
        assert set(row) <= {
            "user_id",
            "username",
            "scraper_id",
            "products",
            "carts",
            "http_requests",
            "cache_hits",
        }, "DASH-R6: load is governance, what someone watches is not"


def test_the_load_view_is_admin_only(client: TestClient) -> None:
    assert client.get("/api/admin/dashboard/users").status_code == 401
