"""Email notifier tests (phase 7.B5–7.B7): formatting, SMTP delivery, retry/error contract.

The plugin is fetched from the loaded app (conftest loads the real plugins); ``smtplib.SMTP`` is
monkeypatched with a fake so no real connection is made.
"""

from __future__ import annotations

import smtplib
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.core.alert_engine import AlertEvent, CartAlertPayload, CartTotals, ProductAlertPayload
from src.core.contracts import AlertType
from src.core.plugins.base import NotifierDeliveryError, NotifierPlugin

_CONFIG = {
    "smtp_host": "smtp.local",
    "smtp_port": 1025,
    "use_tls": False,
    "from_address": "watch@local",
    "to_address": "user@local",
}


def _email(client: TestClient) -> NotifierPlugin:
    for lp in client.app.state.loaded_plugins:  # type: ignore[attr-defined]
        if lp.plugin.plugin_id == "email":
            assert isinstance(lp.plugin, NotifierPlugin)
            return lp.plugin
    raise AssertionError("email plugin not loaded")


class _FakeSMTP:
    sent: list[Any] = []

    def __init__(self, host: str, port: int, timeout: float | None = None) -> None:
        self.host = host

    def __enter__(self) -> _FakeSMTP:
        return self

    def __exit__(self, *_a: object) -> None:
        return None

    def starttls(self, context: object = None) -> None:
        pass

    def login(self, user: str, password: str) -> None:
        pass

    def send_message(self, msg: Any) -> None:
        _FakeSMTP.sent.append(msg)


def _digest() -> AlertEvent:
    product = ProductAlertPayload(
        product_id=1,
        name="Widget",
        url="https://shop/x",
        plugin_id="dragon_store",
        tags=[AlertType.PRODUCT_ON_SALE],
        price_previous=Decimal("50.00"),
        price_current=Decimal("39.90"),
        discount_pct=Decimal("20"),
        currency="EUR",
    )
    cart = CartAlertPayload(
        cart_id=1,
        cart_name="My cart",
        mode="cross",
        products=[product],
        totals=CartTotals(
            full=Decimal("50.00"), discounted=Decimal("39.90"), final=Decimal("39.90")
        ),
    )
    return AlertEvent(user_id=1, generated_at=datetime.now(UTC), cart_alerts=[cart])


def test_send_test_builds_html_and_text(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _FakeSMTP.sent = []
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    _email(client).send_test(_CONFIG, "en")
    assert len(_FakeSMTP.sent) == 1
    msg = _FakeSMTP.sent[0]
    assert "test email" in msg["Subject"]
    body = msg.as_string()
    assert "text/html" in body and "text/plain" in body  # HTML + text fallback


def test_send_digest_keeps_provenance_and_prices(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _FakeSMTP.sent = []
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    _email(client).send(_digest(), _CONFIG, "en")
    body = _FakeSMTP.sent[0].as_string()
    assert "dragon_store" in body  # provenance (NOT-R7)
    assert "39.90" in body and "50.00" in body  # before/after prices


def test_missing_config_raises(client: TestClient) -> None:
    with pytest.raises(NotifierDeliveryError):
        _email(client).send_test({"smtp_host": "h"}, "en")  # no from/to


def test_transient_error_retries_then_fails(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = {"n": 0}

    def _boom(*_a: object, **_k: object) -> None:
        calls["n"] += 1
        raise OSError("connection refused")

    plugin = _email(client)
    monkeypatch.setattr(plugin, "backoff_base_s", 0.0)  # keep the test fast
    monkeypatch.setattr(smtplib, "SMTP", _boom)
    with pytest.raises(NotifierDeliveryError, match="unreachable"):
        plugin.send_test(_CONFIG, "en")
    assert calls["n"] == 3  # 3 attempts (email default retries), not a single try


def test_recipient_refused_fails_immediately(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _Refuse(_FakeSMTP):
        def send_message(self, msg: Any) -> None:
            raise smtplib.SMTPRecipientsRefused({"user@local": (550, b"no")})

    monkeypatch.setattr(smtplib, "SMTP", _Refuse)
    with pytest.raises(NotifierDeliveryError, match="recipient refused"):
        _email(client).send_test(_CONFIG, "en")
