from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_CONFIG = (
    "core:\n"
    '  database_url: "sqlite+pysqlite:///:memory:"\n'
    '  secret_key: "${WEA_SECRET_KEY}"\n'
    '  default_locale: "en"\n'
    "  access_token_ttl_min: 15\n"
    "  refresh_token_ttl_days: 7\n"
)


@pytest.fixture()
def app(tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> Iterator[FastAPI]:
    """The configured application, **not** started: the lifespan has not run yet. Almost every
    test wants `client` below instead; take this one only to drive startup/shutdown yourself."""
    cfg = tmp_path / "config.yaml"  # type: ignore[operator]
    cfg.write_text(_CONFIG, encoding="utf-8")
    ver = tmp_path / "VERSION"  # type: ignore[operator]
    ver.write_text("9.9.9-test\n", encoding="utf-8")

    monkeypatch.setenv("WEA_SECRET_KEY", "x" * 64)
    monkeypatch.setenv("WEA_ADMIN_INITIAL_USERNAME", "admin")
    monkeypatch.setenv("WEA_ADMIN_INITIAL_PASSWORD", "initpass123")

    from src.core import config as config_mod
    from src.core.rate_limit import RateLimiter

    monkeypatch.setattr(config_mod, "CONFIG_PATH", str(cfg))
    monkeypatch.setattr(config_mod, "VERSION_PATH", str(ver))
    config_mod.get_settings.cache_clear()

    from src.core import http as http_mod
    from src.web.app import create_app
    from src.web.routers import auth as auth_mod

    # Web tests must never actually wait. The shipped politeness floor is 11 s (what
    # Dragon Store's robots.txt asks for), and every client the core builds for a plugin
    # honours it — including the ones built inside a request. Neutralising the wait here,
    # on the class, covers every builder without touching production wiring; the real
    # politeness arithmetic stays fully covered by tests/core/test_http_client.py.
    monkeypatch.setattr(http_mod.HttpClient, "_wait_before", lambda self, attempt, interval_s: None)

    # Fresh limiter per test so login attempts don't accumulate across tests.
    monkeypatch.setattr(
        auth_mod, "_login_limiter", RateLimiter(max_attempts=5, window_seconds=60.0)
    )

    yield create_app()
    config_mod.get_settings.cache_clear()


@pytest.fixture()
def client(app: FastAPI) -> Iterator[TestClient]:
    """The started application: entering the context runs the lifespan (schema, admin
    bootstrap, plugins), leaving it runs the shutdown half."""
    with TestClient(app) as test_client:
        yield test_client
