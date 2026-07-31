"""Tests for the scrape cache (4.B8, CTX-R9): key normalisation, the read-through
backend, the half-life, and the HttpClient integration."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from src.core.db import get_engine, new_session
from src.core.http import HttpClient
from src.core.models import ScrapeCache as ScrapeCacheRow
from src.core.scrape_cache import ScrapeCache, cache_key, clear, purge_expired

URL = "http://shop.test/cat?b=2&a=1"


def test_cache_key_normalizes() -> None:
    # Param order and fragment don't matter; host case doesn't matter.
    assert cache_key("p", "GET", "http://h/x?a=1&b=2") == cache_key(
        "p", "GET", "http://h/x?b=2&a=1"
    )
    assert cache_key("p", "GET", "http://h/x#frag") == cache_key("p", "GET", "http://h/x")
    assert cache_key("p", "GET", "http://H/x") == cache_key("p", "GET", "http://h/x")
    # Method, path and plugin scope DO matter.
    assert cache_key("p", "GET", "http://h/x") != cache_key("p", "POST", "http://h/x")
    assert cache_key("p", "GET", "http://h/x") != cache_key("p", "GET", "http://h/y")
    assert cache_key("p", "GET", "http://h/x") != cache_key("q", "GET", "http://h/x")


def test_get_miss_then_put_then_hit(client: TestClient) -> None:
    cache = ScrapeCache(get_engine(), "p1", ttl_min=60)
    assert cache.get("GET", URL) is None
    cache.put("GET", URL, 200, b"<html>hi</html>", "text/html; charset=utf-8")
    hit = cache.get("GET", URL)
    assert hit is not None
    assert hit.status_code == 200
    assert hit.content == b"<html>hi</html>"
    assert hit.content_type == "text/html; charset=utf-8"
    # A POST to the same URL is a different key — not served from the GET entry.
    assert cache.get("POST", URL) is None


def test_disabled_when_ttl_zero(client: TestClient) -> None:
    cache = ScrapeCache(get_engine(), "p1", ttl_min=0)
    assert cache.enabled is False
    cache.put("GET", URL, 200, b"x", "text/html")
    assert cache.get("GET", URL) is None  # nothing written, nothing read


def test_expired_entry_is_a_miss(client: TestClient) -> None:
    now = datetime.now(UTC)
    session = new_session()
    try:
        session.add(
            ScrapeCacheRow(
                plugin_id="p1",
                cache_key=cache_key("p1", "GET", URL),
                response_body=b"old",
                response_meta_json={"status": 200, "content_type": "text/html"},
                fetched_at=now - timedelta(minutes=120),
                expires_at=now - timedelta(minutes=1),  # already expired
            )
        )
        session.commit()
    finally:
        session.close()
    assert ScrapeCache(get_engine(), "p1", ttl_min=60).get("GET", URL) is None


def test_httpclient_serves_from_cache_without_http(client: TestClient) -> None:
    cache = ScrapeCache(get_engine(), "p1", ttl_min=60)
    cache.put("GET", URL, 200, b"<html>cached</html>", "text/html")
    http = HttpClient(cache=cache)
    resp = http.get(URL)
    assert resp.status_code == 200
    assert resp.content == b"<html>cached</html>"
    assert http.request_count == 0  # no real HTTP made
    assert http.cache_hits == 1
    # A second read is another hit, still no HTTP.
    http.get(URL)
    assert http.request_count == 0
    assert http.cache_hits == 2


def test_cache_hit_carries_the_original_fetch_time(client: TestClient) -> None:
    """A replayed response must date itself to the fetch that filled the cache, not to the
    replay: ``last_seen_at`` is derived from it, and getting this wrong made a page up to a
    half-life old look like it had just been read."""
    fetched = datetime.now(UTC) - timedelta(hours=6)
    session = new_session()
    try:
        session.add(
            ScrapeCacheRow(
                plugin_id="p1",
                cache_key=cache_key("p1", "GET", URL),
                response_body=b"<html>old but valid</html>",
                response_meta_json={"status": 200, "content_type": "text/html"},
                fetched_at=fetched,
                expires_at=datetime.now(UTC) + timedelta(hours=6),
            )
        )
        session.commit()
    finally:
        session.close()

    hit = ScrapeCache(get_engine(), "p1", ttl_min=720).get("GET", URL)
    assert hit is not None
    assert abs((hit.fetched_at - fetched).total_seconds()) < 1

    resp = HttpClient(cache=ScrapeCache(get_engine(), "p1", ttl_min=720)).get(URL)
    assert resp.fetched_at is not None
    assert abs((resp.fetched_at - fetched).total_seconds()) < 1


def _seed(plugin_id: str, url: str, expires: datetime) -> None:
    session = new_session()
    try:
        session.add(
            ScrapeCacheRow(
                plugin_id=plugin_id,
                cache_key=cache_key(plugin_id, "GET", url),
                response_body=b"x",
                response_meta_json={"status": 200, "content_type": "text/html"},
                fetched_at=datetime.now(UTC),
                expires_at=expires,
            )
        )
        session.commit()
    finally:
        session.close()


def test_purge_expired_removes_only_expired_for_plugin(client: TestClient) -> None:
    now = datetime.now(UTC)
    _seed("p1", "http://h/expired", now - timedelta(minutes=1))
    _seed("p1", "http://h/fresh", now + timedelta(minutes=30))
    _seed("p2", "http://h/expired", now - timedelta(minutes=1))  # other plugin, untouched
    session = new_session()
    try:
        assert purge_expired(session, "p1", now) == 1
        assert ScrapeCache(get_engine(), "p1").get("GET", "http://h/fresh") is not None
        assert ScrapeCache(get_engine(), "p2").get("GET", "http://h/expired") is None  # expired
    finally:
        session.close()


def test_clear_removes_all_for_plugin_only(client: TestClient) -> None:
    now = datetime.now(UTC)
    _seed("p1", "http://h/a", now + timedelta(minutes=30))
    _seed("p1", "http://h/b", now + timedelta(minutes=30))
    _seed("p2", "http://h/a", now + timedelta(minutes=30))
    session = new_session()
    try:
        assert clear(session, "p1") == 2
        assert ScrapeCache(get_engine(), "p1").get("GET", "http://h/a") is None
        assert ScrapeCache(get_engine(), "p2").get("GET", "http://h/a") is not None
    finally:
        session.close()
