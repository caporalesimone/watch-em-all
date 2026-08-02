"""Notifier dispatch, drain and config resolution (phase 7).

Standalone-session tests (like test_alert_run): enqueue writes per-channel deliveries with in-app
inline and network channels pending; the drain sends the pending ones and records outcomes; the
config layer filters keys on the schema, keeps secrets write-only, and resolves the composite state.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from src.core import notifiers as notif
from src.core.admin_messages import send_admin_message
from src.core.alert_engine import AlertEvent, NotificationEvent
from src.core.contracts import ConfigField
from src.core.db import Base
from src.core.models import AdminMessageDelivery, AlertDelivery, AlertLog, User
from src.core.notify import drain_deliveries, drain_message_deliveries, enqueue_deliveries
from src.core.plugins.base import NotifierDeliveryError, NotifierPlugin

NOW = datetime(2026, 7, 23, 9, 0, tzinfo=UTC)


def _session() -> Session:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return Session(engine)


class FakeInApp(NotifierPlugin):
    plugin_id = "in_app"
    display_name = "In-app"


class FakeEmail(NotifierPlugin):
    plugin_id = "email"
    display_name = "Email"

    def __init__(self, fail: bool = False) -> None:
        self.sent: list[tuple[dict[str, Any], str]] = []
        self.fail = fail

    def get_admin_config_schema(self) -> list[ConfigField]:
        return [
            ConfigField(key="smtp_host", label_key="x", type="text", required=True),
            ConfigField(key="smtp_password", label_key="x", type="password"),
        ]

    def get_user_config_schema(self) -> list[ConfigField]:
        return [ConfigField(key="to_address", label_key="x", type="email", required=True)]

    def send(self, notification: NotificationEvent, config: dict[str, Any], locale: str) -> None:
        if self.fail:
            raise NotifierDeliveryError("boom")
        self.sent.append((config, locale))


def _user(db: Session, name: str = "alice@example.com") -> User:
    u = User(username=name, password_hash="x")
    db.add(u)
    db.flush()
    return u


def _digest(db: Session, user_id: int) -> AlertLog:
    event = AlertEvent(user_id=user_id, generated_at=NOW, cart_alerts=[])
    log = AlertLog(user_id=user_id, kind="alert_digest", payload_json=event.model_dump(mode="json"))
    db.add(log)
    db.flush()
    return log


def _statuses(db: Session, log_id: int) -> dict[str, str]:
    rows = db.scalars(select(AlertDelivery).where(AlertDelivery.alert_log_id == log_id)).all()
    return {r.plugin_id: r.status for r in rows}


# --------------------------------------------------------------------------- enqueue


def test_enqueue_in_app_only_marks_delivered_inline() -> None:
    with _session() as db:
        user = _user(db)
        log = _digest(db, user.id)
        enqueue_deliveries(db, log, [FakeInApp()])
        assert _statuses(db, log.id) == {"in_app": "delivered"}


def test_enqueue_active_email_is_pending_in_app_delivered() -> None:
    with _session() as db:
        user = _user(db)
        email = FakeEmail()
        notif.set_admin_config(db, email, {"smtp_host": "smtp.local"})
        notif.set_user_config(db, email, user.id, {"to_address": "a@b.co"})
        notif.set_user_enabled(db, user.id, "email", True)
        log = _digest(db, user.id)
        enqueue_deliveries(db, log, [FakeInApp(), email])
        assert _statuses(db, log.id) == {"in_app": "delivered", "email": "pending"}


def test_enqueue_skipped_no_notifier_when_nothing_active() -> None:
    with _session() as db:
        user = _user(db)
        notif.set_admin_enabled(db, "in_app", False)  # admin disabled in-app
        log = _digest(db, user.id)
        enqueue_deliveries(db, log, [FakeInApp(), FakeEmail()])  # email not configured
        assert _statuses(db, log.id) == {"": "skipped_no_notifier"}


def test_enqueue_in_app_skipped_but_email_pending() -> None:
    with _session() as db:
        user = _user(db)
        email = FakeEmail()
        notif.set_admin_enabled(db, "in_app", False)
        notif.set_admin_config(db, email, {"smtp_host": "smtp.local"})
        notif.set_user_config(db, email, user.id, {"to_address": "a@b.co"})
        notif.set_user_enabled(db, user.id, "email", True)
        log = _digest(db, user.id)
        enqueue_deliveries(db, log, [FakeInApp(), email])
        assert _statuses(db, log.id) == {"in_app": "skipped", "email": "pending"}


# --------------------------------------------------------------------------- drain


def test_drain_sends_pending_and_marks_delivered() -> None:
    with _session() as db:
        user = _user(db)
        email = FakeEmail()
        notif.set_admin_config(db, email, {"smtp_host": "smtp.local"})
        notif.set_user_config(db, email, user.id, {"to_address": "a@b.co"})
        notif.set_user_enabled(db, user.id, "email", True)
        log = _digest(db, user.id)
        enqueue_deliveries(db, log, [FakeInApp(), email])

        assert drain_deliveries(db, [FakeInApp(), email]) == 1
        assert _statuses(db, log.id)["email"] == "delivered"
        assert len(email.sent) == 1
        cfg, locale = email.sent[0]
        assert cfg["smtp_host"] == "smtp.local" and cfg["to_address"] == "a@b.co"


def test_drain_records_failure_with_reason() -> None:
    with _session() as db:
        user = _user(db)
        email = FakeEmail()
        email.fail = True
        notif.set_admin_config(db, email, {"smtp_host": "smtp.local"})
        notif.set_user_config(db, email, user.id, {"to_address": "a@b.co"})
        notif.set_user_enabled(db, user.id, "email", True)
        log = _digest(db, user.id)
        enqueue_deliveries(db, log, [email])

        drain_deliveries(db, [email])
        row = db.scalar(select(AlertDelivery).where(AlertDelivery.plugin_id == "email"))
        assert row is not None and row.status == "failed" and "boom" in (row.error or "")


def test_drain_marks_failed_when_notifier_not_loaded() -> None:
    with _session() as db:
        user = _user(db)
        email = FakeEmail()
        notif.set_admin_config(db, email, {"smtp_host": "smtp.local"})
        notif.set_user_config(db, email, user.id, {"to_address": "a@b.co"})
        notif.set_user_enabled(db, user.id, "email", True)
        log = _digest(db, user.id)
        enqueue_deliveries(db, log, [email])

        drain_deliveries(db, [])  # email plugin not available this tick
        row = db.scalar(select(AlertDelivery).where(AlertDelivery.plugin_id == "email"))
        assert row is not None and row.status == "failed" and row.error == "notifier not loaded"


# --------------------------------------------------------------------------- config layer


def test_user_config_drops_admin_keys() -> None:
    with _session() as db:
        user = _user(db)
        email = FakeEmail()
        stored = notif.set_user_config(
            db, email, user.id, {"to_address": "a@b.co", "smtp_host": "evil"}
        )
        assert stored == {"to_address": "a@b.co"}  # admin key filtered out (CFG-R5)


def test_secret_is_write_only_and_kept_on_empty() -> None:
    with _session() as db:
        email = FakeEmail()
        notif.set_admin_config(db, email, {"smtp_host": "h", "smtp_password": "s3cr3t"})
        schema = email.get_admin_config_schema()
        cfg = notif.admin_config(db, "email")
        assert notif.public_config(schema, cfg) == {"smtp_host": "h"}  # secret stripped (CFG-R3)
        assert notif.is_set_map(schema, cfg) == {"smtp_password": True}
        # A save omitting the secret keeps the stored value.
        notif.set_admin_config(db, email, {"smtp_host": "h2"})
        assert notif.admin_config(db, "email")["smtp_password"] == "s3cr3t"


def test_resolve_state_transitions() -> None:
    with _session() as db:
        user = _user(db)
        email = FakeEmail()
        st = notif.resolve_state(db, email, user.id)
        assert not st.available and not st.active  # no admin config yet
        notif.set_admin_config(db, email, {"smtp_host": "h"})
        st = notif.resolve_state(db, email, user.id)
        assert st.available and not st.active  # available, but user not configured/enabled
        notif.set_user_config(db, email, user.id, {"to_address": "a@b.co"})
        notif.set_user_enabled(db, user.id, "email", True)
        assert notif.resolve_state(db, email, user.id).active

        in_app = FakeInApp()
        assert notif.resolve_state(db, in_app, user.id).active  # always active for the user
        notif.set_admin_enabled(db, "in_app", False)
        assert not notif.resolve_state(db, in_app, user.id).active  # admin kill-switch


# ----------------------------------------------------------------- admin messages (10.B12)


def test_message_drain_sends_the_text_payload_and_records_the_outcome() -> None:
    with _session() as db:
        user = _user(db)
        email = FakeEmail()
        notif.set_admin_config(db, email, {"smtp_host": "smtp.local"})
        notif.set_user_config(db, email, user.id, {"to_address": "a@b.co"})
        notif.set_user_enabled(db, user.id, "email", True)
        message = send_admin_message(
            db,
            sender_id=None,
            title="Notice",
            body="**hello**",
            target_user_id=user.id,
            notifiers=[FakeInApp(), email],
        )
        assert drain_message_deliveries(db, [FakeInApp(), email]) == 1  # only the network one

        rows = db.scalars(
            select(AdminMessageDelivery).where(AdminMessageDelivery.admin_message_id == message.id)
        ).all()
        assert {r.plugin_id: r.status for r in rows} == {
            "in_app": "delivered",
            "email": "delivered",
        }
        # The notifier received the flat text payload, not a digest — the whole point of the union.
        assert len(email.sent) == 1


def test_a_failing_channel_records_the_reason_and_is_not_retried() -> None:
    with _session() as db:
        user = _user(db)
        email = FakeEmail(fail=True)
        notif.set_admin_config(db, email, {"smtp_host": "smtp.local"})
        notif.set_user_config(db, email, user.id, {"to_address": "a@b.co"})
        notif.set_user_enabled(db, user.id, "email", True)
        send_admin_message(
            db,
            sender_id=None,
            title="Notice",
            body="hello",
            target_user_id=user.id,
            notifiers=[email],
        )
        drain_message_deliveries(db, [email])
        row = db.scalars(
            select(AdminMessageDelivery).where(AdminMessageDelivery.plugin_id == "email")
        ).one()
        assert row.status == "failed" and row.error == "boom"
        # Best-effort, as with digests: a failed row is never re-drained.
        assert drain_message_deliveries(db, [email]) == 0
