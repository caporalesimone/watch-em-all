"""The daily account purge (10.B5, USR-R9/R10).

What is worth testing here is not "the row goes away" but the **order and the abort**:
plugins first, core last, and no core deletion at all if any plugin failed. A half-deleted
account is the one outcome nobody can recover from — the row that could still be found is
gone, while some of its data is not.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.core import user_purge
from src.core.models import Cart, PriceHistory, User
from src.core.plugins.registry import LoadedPlugin
from src.core.user_purge import purge_due_users

NOW = datetime(2026, 8, 2, 12, 0, tzinfo=UTC)


@pytest.fixture()
def session() -> Iterator[Session]:
    from src.core.db import create_schema, init_engine, new_session

    init_engine("sqlite+pysqlite:///:memory:")
    create_schema()
    s = new_session()
    try:
        yield s
    finally:
        s.close()


def _user(session: Session, username: str, *, due: datetime | None) -> int:
    user = User(
        username=username,
        first_name="T",
        last_name="U",
        password_hash="x",
        role="user",
        is_active=due is None,
        deletion_marked_at=None if due is None else due - timedelta(days=30),
        deletion_due_at=due,
    )
    session.add(user)
    session.commit()
    return int(user.id)


class _Plugin:
    """The narrowest stand-in that matters: does it delete, and does it raise?"""

    def __init__(self, plugin_id: str, *, fails: bool = False) -> None:
        self.plugin_id = plugin_id
        self.fails = fails
        self.called_for: list[int] = []

    def delete_user_data(self, _context: Any, user_id: int) -> None:
        self.called_for.append(user_id)
        if self.fails:
            raise RuntimeError("its table is on fire")


class _Loaded:
    def __init__(self, plugin: _Plugin) -> None:
        self.plugin = plugin
        self.manifest = None


def _loaded(*plugins: _Plugin) -> list[LoadedPlugin]:
    """Stand-ins in the shape the purge consumes; it only ever calls delete_user_data."""
    return cast(list[LoadedPlugin], [_Loaded(p) for p in plugins])


@pytest.fixture(autouse=True)
def _no_real_contexts(monkeypatch: pytest.MonkeyPatch) -> None:
    """A context needs an engine and a manifest; this test is about sequencing, not wiring."""

    class _Ctx:
        db = type("_Db", (), {"close": lambda self: None})()

    monkeypatch.setattr(user_purge, "build_context", lambda _m, _p: _Ctx())


def test_only_accounts_past_their_deadline_are_touched(session: Session) -> None:
    live = _user(session, "live", due=None)
    later = _user(session, "later", due=NOW + timedelta(days=1))
    overdue = _user(session, "overdue", due=NOW - timedelta(seconds=1))

    assert purge_due_users(session, NOW, []) == 1

    remaining = set(session.scalars(select(User.id)))
    assert remaining == {live, later}, "marked is not due, and unmarked is not marked"
    assert overdue not in remaining


def test_plugins_are_asked_first_and_the_core_row_goes_last(session: Session) -> None:
    uid = _user(session, "gone", due=NOW - timedelta(days=1))
    one, two = _Plugin("one"), _Plugin("two")

    assert purge_due_users(session, NOW, _loaded(one, two)) == 1

    assert one.called_for == [uid] and two.called_for == [uid]
    assert session.get(User, uid) is None


def test_a_plugin_that_fails_leaves_the_account_marked_for_tomorrow(session: Session) -> None:
    uid = _user(session, "stuck", due=NOW - timedelta(days=1))
    broken, healthy = _Plugin("broken", fails=True), _Plugin("healthy")

    assert purge_due_users(session, NOW, _loaded(broken, healthy)) == 0

    survivor = session.get(User, uid)
    assert survivor is not None, "a partial deletion is worse than a late one"
    assert survivor.deletion_marked_at is not None, "still marked, so tomorrow tries again"
    # The plugins after the broken one are not even asked: there is nothing to gain from
    # deleting more of an account that is going to survive anyway.
    assert healthy.called_for == []


def test_one_stuck_account_does_not_block_the_others(session: Session) -> None:
    _user(session, "stuck", due=NOW - timedelta(days=2))
    _user(session, "fine", due=NOW - timedelta(days=1))

    class _OnlyTheFirstFails(_Plugin):
        def delete_user_data(self, _context: Any, user_id: int) -> None:
            self.called_for.append(user_id)
            if len(self.called_for) == 1:
                raise RuntimeError("not this one")

    assert purge_due_users(session, NOW, _loaded(_OnlyTheFirstFails("p"))) == 1
    assert {u.username for u in session.scalars(select(User))} == {"stuck"}


def test_the_core_cascade_takes_the_carts_and_leaves_the_price_history(session: Session) -> None:
    uid = _user(session, "gone", due=NOW - timedelta(days=1))
    session.add(Cart(user_id=uid, name="Wishlist", mode="cross"))
    session.add(
        PriceHistory(
            plugin_id="dragon_store",
            external_id="896",
            price_current=10,
            price_original=10,
            discount_pct=0,
            is_available=True,
            recorded_at=NOW,
        )
    )
    session.commit()

    purge_due_users(session, NOW, [])

    assert session.scalar(select(func.count()).select_from(Cart)) == 0
    # Phase 9 made the history the product's: it has no foreign key to the user on purpose,
    # and it must survive the person who happened to be watching.
    assert session.scalar(select(func.count()).select_from(PriceHistory)) == 1


# --- the nightly maintenance window (10.B8a) and the alert cap (10.B8b) ------------------


def test_the_window_opens_at_the_local_hour_and_only_once_a_day() -> None:
    from zoneinfo import ZoneInfo

    from src.worker.main import _maintenance_due

    rome = ZoneInfo("Europe/Rome")
    # 05:00 UTC is 07:00 in Rome — the point of interpreting the hour locally.
    before = datetime(2026, 8, 2, 4, 30, tzinfo=UTC)
    after = datetime(2026, 8, 2, 5, 30, tzinfo=UTC)

    assert _maintenance_due(before, rome, 7, None) is False
    assert _maintenance_due(after, rome, 7, None) is True
    # Already done today → not again, however many ticks go by.
    assert _maintenance_due(after, rome, 7, after.astimezone(rome).date()) is False
    # Down at 07:00, up at 11:00 → it still runs. A reboot at the wrong moment must not
    # silently cost a day of housekeeping.
    late = datetime(2026, 8, 2, 9, 0, tzinfo=UTC)
    assert _maintenance_due(late, rome, 7, None) is True


def test_alerts_are_capped_per_person_not_globally(session: Session) -> None:
    from src.core.maintenance import purge_alerts_over_limit
    from src.core.models import AlertLog

    noisy = _user(session, "noisy", due=None)
    quiet = _user(session, "quiet", due=None)
    for i in range(10):
        session.add(
            AlertLog(
                user_id=noisy,
                kind="alert_digest",
                payload_json={"n": i},
                created_at=NOW + timedelta(minutes=i),
            )
        )
    for i in range(2):
        session.add(
            AlertLog(
                user_id=quiet,
                kind="alert_digest",
                payload_json={"n": i},
                created_at=NOW + timedelta(minutes=i),
            )
        )
    session.commit()

    assert purge_alerts_over_limit(session, 3) == 7

    left = list(session.scalars(select(AlertLog).where(AlertLog.user_id == noisy)))
    assert len(left) == 3
    assert {row.payload_json["n"] for row in left} == {7, 8, 9}, "the most recent survive"
    # The quiet account is under the cap and is not touched: one heavy user must not push
    # everybody else's history out.
    assert (
        session.scalar(select(func.count()).select_from(AlertLog).where(AlertLog.user_id == quiet))
        == 2
    )


def test_a_cap_of_zero_keeps_everything(session: Session) -> None:
    from src.core.maintenance import purge_alerts_over_limit
    from src.core.models import AlertLog

    uid = _user(session, "someone", due=None)
    session.add(AlertLog(user_id=uid, kind="alert_digest", payload_json={}, created_at=NOW))
    session.commit()
    assert purge_alerts_over_limit(session, 0) == 0
    assert session.scalar(select(func.count()).select_from(AlertLog)) == 1
