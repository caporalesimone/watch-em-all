"""Tests for the per-scraper core reserved config service (4.B10)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.core.db import new_session
from src.core.http import DEFAULT_MIN_INTERVAL_S, DEFAULT_TIMEOUT_S
from src.core.models import ScraperAdminConfig
from src.core.scrape import SCRAPE_NOW_COOLDOWN_SECONDS
from src.core.scrape_cache import DEFAULT_CACHE_TTL_MIN
from src.core.scraper_config import get_scraper_config, set_scraper_config


def test_defaults_mirror_constants_when_no_row(client: TestClient) -> None:
    session = new_session()
    try:
        cfg = get_scraper_config(session, "dragon_store")
        assert cfg.politeness_delay_ms == round(DEFAULT_MIN_INTERVAL_S * 1000)
        assert cfg.http_timeout_s == DEFAULT_TIMEOUT_S
        assert cfg.cache_ttl_min == DEFAULT_CACHE_TTL_MIN
        assert cfg.scrape_now_min_interval_s == SCRAPE_NOW_COOLDOWN_SECONDS
    finally:
        session.close()


def test_set_merges_partial_and_persists(client: TestClient) -> None:
    session = new_session()
    try:
        set_scraper_config(session, "dragon_store", {"cache_ttl_min": 10})
        cfg = get_scraper_config(session, "dragon_store")
        assert cfg.cache_ttl_min == 10
        assert cfg.http_timeout_s == DEFAULT_TIMEOUT_S  # untouched key keeps its default
        # A second partial set merges over the current values, never resets the rest.
        set_scraper_config(session, "dragon_store", {"http_timeout_s": 22})
        cfg = get_scraper_config(session, "dragon_store")
        assert cfg.cache_ttl_min == 10
        assert cfg.http_timeout_s == 22
    finally:
        session.close()


def test_unknown_key_rejected(client: TestClient) -> None:
    session = new_session()
    try:
        with pytest.raises(ValueError):
            set_scraper_config(session, "dragon_store", {"nope": 1})
    finally:
        session.close()


def test_out_of_range_rejected(client: TestClient) -> None:
    session = new_session()
    try:
        with pytest.raises(ValidationError):
            set_scraper_config(session, "dragon_store", {"http_timeout_s": 999})
    finally:
        session.close()


def test_non_reserved_keys_are_preserved(client: TestClient) -> None:
    # A future plugin-declared field living in the same config_json must survive a
    # reserved-key update (the two share one row, schema.md / PCFG-R2).
    session = new_session()
    try:
        session.add(ScraperAdminConfig(plugin_id="dragon_store", config_json={"site_rule": "x"}))
        session.commit()
        set_scraper_config(session, "dragon_store", {"cache_ttl_min": 5})
        row = session.get(ScraperAdminConfig, "dragon_store")
        assert row is not None
        assert row.config_json["site_rule"] == "x"
        assert row.config_json["cache_ttl_min"] == 5
    finally:
        session.close()
