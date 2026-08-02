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
        # The last politeness knob to leave the code (10.B22).
        "http_retries": 2,
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


# --------------------------------------------------- the config a scraper declares (10.B22)

PCFG = "/api/admin/scrapers/dragon_store/plugin-config"


def test_a_scraper_declares_its_own_settings(client: TestClient) -> None:
    """10.B22. Until now no scraper declared a schema, which is why 10.F13 was a form with
    nothing to render — the thresholds sat hard-wired in `adjustments.py` under a phase-5 note
    promising this move."""
    h = _bearer(_admin_token(client))
    body = client.get(PCFG, headers=h).json()
    keys = {f["key"] for f in body["schema_fields"]}
    assert {"band1_min", "band1_pct", "shipping_cost", "free_shipping_min"} <= keys
    assert body["config"]["band1_min"] == 100
    # A declared key may never shadow one the core reads on the plugin's behalf.
    assert not keys & {"politeness_delay_ms", "http_timeout_s", "cache_ttl_min"}


def test_declared_and_reserved_settings_do_not_overwrite_each_other(client: TestClient) -> None:
    """Both live in the same `config_json`, so this is the failure worth a test: saving one
    side must leave the other exactly where it was."""
    h = _bearer(_admin_token(client))
    client.patch(CFG, json={"cache_ttl_min": 0}, headers=h)
    client.put(PCFG, json={"config": {"band1_min": 50, "shipping_cost": 7}}, headers=h)

    assert client.get(CFG, headers=h).json()["cache_ttl_min"] == 0
    saved = client.get(PCFG, headers=h).json()["config"]
    assert saved["band1_min"] == 50 and saved["shipping_cost"] == 7

    # And the reverse: touching the reserved side leaves the declared values alone.
    client.patch(CFG, json={"http_timeout_s": 20}, headers=h)
    assert client.get(PCFG, headers=h).json()["config"]["band1_min"] == 50


def test_a_saved_threshold_changes_the_next_evaluation(client: TestClient) -> None:
    """The MVP's own check: the numbers move without a restart. The plugin caches the rules it
    builds from them, so this is really a test that the cache is dropped when they change."""
    from decimal import Decimal

    from src.core.plugins.base import ScraperPlugin

    h = _bearer(_admin_token(client))
    loaded = [
        lp.plugin
        for lp in client.app.state.loaded_plugins  # type: ignore[attr-defined]
        if isinstance(lp.plugin, ScraperPlugin) and lp.plugin.plugin_id == "dragon_store"
    ]
    plugin = loaded[0]

    # Default: shipping costs 5 below the free threshold of 100.
    before = plugin.get_adjustments([], Decimal("50"))
    assert any(a.amount == Decimal("-5.00") for a in before)

    client.put(PCFG, json={"config": {"shipping_cost": 9, "free_shipping_min": 500}}, headers=h)
    after = plugin.get_adjustments([], Decimal("50"))
    assert any(a.amount == Decimal("-9") for a in after), "the new cost, with no restart"
