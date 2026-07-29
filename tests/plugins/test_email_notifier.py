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


def _product(previous: str | None, current: str, discount: str = "20") -> ProductAlertPayload:
    return ProductAlertPayload(
        product_id=1,
        name="Widget",
        url="https://shop/x",
        plugin_id="dragon_store",
        tags=[AlertType.PRODUCT_ON_SALE],
        price_previous=Decimal(previous) if previous is not None else None,
        price_current=Decimal(current),
        discount_pct=Decimal(discount),
        currency="EUR",
    )


def _digest(product: ProductAlertPayload | None = None) -> AlertEvent:
    product = product or _product("50.00", "39.90")
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
    _email(client).send_test(_CONFIG, "en", "alice")
    assert len(_FakeSMTP.sent) == 1
    msg = _FakeSMTP.sent[0]
    assert "test email" in msg["Subject"]
    body = msg.as_string()
    assert "text/html" in body and "text/plain" in body  # HTML + text fallback
    assert "alice" in body  # dedicated test message names the user
    assert "Sample cart" not in body  # not the fake digest anymore


def test_send_digest_keeps_provenance_and_prices(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _FakeSMTP.sent = []
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    _email(client).send(_digest(), _CONFIG, "en")
    body = _FakeSMTP.sent[0].as_string()
    assert "dragon_store" in body  # provenance (NOT-R7)
    assert "39.90" in body and "50.00" in body  # before/after prices


def _parts(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, product: ProductAlertPayload
) -> tuple[str, str]:
    """Send one digest and return its decoded (html, text) bodies — decoded because
    quoted-printable folds long lines, and a folded `+25%` is not a substring of the raw
    message."""
    _FakeSMTP.sent = []
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    _email(client).send(_digest(product), _CONFIG, "en")
    msg = _FakeSMTP.sent[0]
    html = msg.get_body(preferencelist=("html",)).get_content()
    text = msg.get_body(preferencelist=("plain",)).get_content()
    return str(html), str(text)


def test_difference_column_reports_a_price_rise_as_positive(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Issue #37: an off-sale product whose price went UP printed `-0%`, because the column
    showed the sale discount (legitimately 0) with a hardcoded minus sign, next to a Was/Now
    pair that said the opposite. €39.92 -> €49.90 is +25%."""
    html, text = _parts(client, monkeypatch, _product("39.92", "49.90", discount="0"))
    assert "Difference" in html and "Discount" not in html
    assert "+25%" in html and "+25%" in text
    assert "-0%" not in html and "-0%" not in text


def test_difference_column_reports_a_price_drop_as_negative(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    html, text = _parts(client, monkeypatch, _product("50.00", "39.90"))
    assert "-20.2%" in html and "-20.2%" in text  # one decimal kept when it is not zero


def test_difference_column_handles_no_change_and_no_previous_price(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A digest can carry a product whose price did not move (an availability tag), and the
    payload allows no previous price at all. Neither may render as a signed percentage."""
    html, text = _parts(client, monkeypatch, _product("42.00", "42.00"))
    assert "0%" in html and "+0%" not in html and "-0%" not in html
    assert "(0%)" in text
    html, text = _parts(client, monkeypatch, _product(None, "42.00"))
    assert "—" in html and "(—)" in text


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
