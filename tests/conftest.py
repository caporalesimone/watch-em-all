from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

_CONFIG = (
    "core:\n"
    '  database_url: "sqlite+pysqlite:///:memory:"\n'
    '  secret_key: "${SECRET_KEY}"\n'
    '  default_locale: "en"\n'
    "  access_token_ttl_min: 15\n"
    "  refresh_token_ttl_days: 7\n"
)


@pytest.fixture()
def client(tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    cfg = tmp_path / "config.yaml"  # type: ignore[operator]
    cfg.write_text(_CONFIG, encoding="utf-8")
    ver = tmp_path / "VERSION"  # type: ignore[operator]
    ver.write_text("9.9.9-test\n", encoding="utf-8")

    monkeypatch.setenv("SECRET_KEY", "x" * 64)
    monkeypatch.setenv("ADMIN_INITIAL_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_INITIAL_PASSWORD", "initpass123")

    from src.core import config as config_mod
    from src.core.rate_limit import RateLimiter

    monkeypatch.setattr(config_mod, "CONFIG_PATH", str(cfg))
    monkeypatch.setattr(config_mod, "VERSION_PATH", str(ver))
    config_mod.get_settings.cache_clear()

    from src.web.app import create_app
    from src.web.routers import auth as auth_mod

    # Fresh limiter per test so login attempts don't accumulate across tests.
    monkeypatch.setattr(
        auth_mod, "_login_limiter", RateLimiter(max_attempts=5, window_seconds=60.0)
    )

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
    config_mod.get_settings.cache_clear()
