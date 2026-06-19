"""Tests for the scraper identity template-method (SCR-R10 / product.md).

The seed is the only site-specific point; normalisation and hashing are final
and uniform. Determinism across processes is the property that matters most
(worker vs web must agree), so the hashing is pinned to sha256, never the
PYTHONHASHSEED-randomised built-in ``hash()``.
"""

from __future__ import annotations

import hashlib

import pytest

from src.core.plugins.base import ScraperPlugin


class _Scraper(ScraperPlugin):
    plugin_id = "t"

    def __init__(self, seed: str | None) -> None:
        self._seed = seed

    def identity_seed(self, raw: object) -> str | None:
        return self._seed


def test_normalize_url_strips_volatile_and_lowercases_host() -> None:
    out = ScraperPlugin.normalize_url("HTTPS://Shop.EXAMPLE.com/p/123/?utm=x#frag")
    assert out == "https://shop.example.com/p/123"


def test_normalize_url_is_idempotent() -> None:
    once = ScraperPlugin.normalize_url("https://x.com/a/?q=1")
    assert ScraperPlugin.normalize_url(once) == once


def test_stable_id_is_sha256_prefix_and_deterministic() -> None:
    seed = "35880"
    expected = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    assert ScraperPlugin._stable_id(seed) == expected
    assert ScraperPlugin._stable_id(seed) == ScraperPlugin._stable_id(seed)
    assert len(expected) == 16


def test_external_id_uses_seed_when_present() -> None:
    s = _Scraper(seed="35880")
    assert s.external_id_for(raw=None, url="https://x.com/p.gp.35880.uw") == s._stable_id("35880")


def test_external_id_falls_back_to_normalized_url_when_seed_none() -> None:
    s = _Scraper(seed=None)
    url = "https://X.com/p/9/?utm=1#f"
    assert s.external_id_for(raw=None, url=url) == s._stable_id(ScraperPlugin.normalize_url(url))


def test_same_product_different_volatile_url_same_external_id() -> None:
    """Fallback path: two URLs differing only by query/fragment/host-case map
    to the same id (history stays intact across runs)."""
    s = _Scraper(seed=None)
    a = s.external_id_for(raw=None, url="https://shop.com/p/1?utm=a")
    b = s.external_id_for(raw=None, url="https://SHOP.com/p/1?utm=b#x")
    assert a == b


def test_scraper_without_seed_does_not_instantiate() -> None:
    class _NoSeed(ScraperPlugin):
        plugin_id = "x"

    with pytest.raises(TypeError):
        _NoSeed()  # type: ignore[abstract]
