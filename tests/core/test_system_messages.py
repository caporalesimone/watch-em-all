"""The system-message catalog (ADMSG-R7..R10, 10.B16).

The interesting behaviour is not "does it substitute a placeholder" but the four rules the spec
puts around that: only overrides are stored, resolution happens in one place and one order, an
unknown placeholder is text rather than a crash, and a required one cannot be dropped.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from src.core import system_messages as sysmsg
from src.core.db import new_session
from src.core.models import SystemMessageTemplate, User


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _admin(client: TestClient) -> str:
    login = client.post("/api/auth/login", json={"username": "admin", "password": "initpass123"})
    client.post(
        "/api/auth/change-password",
        json={"new_password": "adminpass123"},
        headers=_bearer(login.json()["access_token"]),
    )
    again = client.post("/api/auth/login", json={"username": "admin", "password": "adminpass123"})
    return str(again.json()["access_token"])


def test_a_key_with_no_row_is_its_default(client: TestClient) -> None:
    """ADMSG-R9: adding a message to the core costs no migration and no seeding, because the
    absence of a row already means something."""
    with new_session() as db:
        assert db.scalars(select(SystemMessageTemplate)).all() == []
        title, body = sysmsg.resolve(db, "user.disabled", first_name="Alice", username="a@b.co")
    assert title == sysmsg.USER_DISABLED.title
    assert "Hello Alice," in body


def test_an_override_wins_and_is_the_only_thing_stored(client: TestClient) -> None:
    with new_session() as db:
        db.add(
            SystemMessageTemplate(
                key="user.disabled", title="Access closed", body="Sorry {first_name}."
            )
        )
        db.commit()
        title, body = sysmsg.resolve(db, "user.disabled", first_name="Alice", username="a@b.co")
        assert (title, body) == ("Access closed", "Sorry Alice.")
        # One row, for the one key that was rewritten — the rest of the catalog is still code.
        assert [r.key for r in db.scalars(select(SystemMessageTemplate))] == ["user.disabled"]


def test_an_unknown_placeholder_is_delivered_as_text(client: TestClient) -> None:
    """ADMSG-R8. The alternative is a 500 at the moment the system has to tell somebody their
    account is going away — a typo in a settings page must not be able to do that."""
    with new_session() as db:
        db.add(
            SystemMessageTemplate(key="user.disabled", title="T", body="Bye {usernme} {first_name}")
        )
        db.commit()
        _, body = sysmsg.resolve(db, "user.disabled", first_name="Alice", username="a@b.co")
    assert body == "Bye {usernme} Alice"


def test_validation_separates_a_typo_from_a_broken_credential(client: TestClient) -> None:
    unknown, missing = sysmsg.validate_override("user.disabled", "T", "Bye {usernme}")
    assert unknown == ["usernme"] and missing == []

    # The one message whose breakage locks a person out (Simone, 2026-08-02).
    unknown, missing = sysmsg.validate_override(
        "user.credentials.created", "T", "Welcome {first_name}"
    )
    assert missing == ["password"]
    unknown, missing = sysmsg.validate_override(
        "user.credentials.created", "T", "Welcome, sign in with {password}"
    )
    assert missing == []


def test_an_unknown_key_is_a_programming_error(client: TestClient) -> None:
    with new_session() as db, pytest.raises(sysmsg.UnknownMessageKey):
        sysmsg.resolve(db, "no.such.message")


# ------------------------------------------------------------------ the courtesy notes (USR-R11)


def _make_user(client: TestClient, admin: str) -> int:
    client.post(
        "/api/admin/users",
        json={
            "username": "alice@example.com",
            "first_name": "Alice",
            "last_name": "Rossi",
            "role": "user",
        },
        headers=_bearer(admin),
    )
    with new_session() as db:
        user = db.scalars(select(User).where(User.username == "alice@example.com")).one()
        return int(user.id)


def _history(user_id: int) -> list[dict[str, object]]:
    from src.core.models import AlertLog

    with new_session() as db:
        rows = db.scalars(
            select(AlertLog).where(AlertLog.user_id == user_id).order_by(AlertLog.id)
        ).all()
        return [dict(r.payload_json) for r in rows]


def test_disabling_an_account_leaves_a_note_in_its_history(client: TestClient) -> None:
    admin = _admin(client)
    uid = _make_user(client, admin)
    client.patch(f"/api/admin/users/{uid}", json={"is_active": False}, headers=_bearer(admin))

    notes = _history(uid)
    assert len(notes) == 1
    assert notes[0]["kind"] == "system_message"
    assert "disabled" in str(notes[0]["title"]).lower()
    # Written even though the account can no longer sign in: if it is ever restored, the
    # explanation is waiting there (USR-R11).

    # Turning it back on says nothing — there is no bad news to break.
    client.patch(f"/api/admin/users/{uid}", json={"is_active": True}, headers=_bearer(admin))
    assert len(_history(uid)) == 1


def test_marking_for_deletion_names_the_date_it_will_happen(client: TestClient) -> None:
    admin = _admin(client)
    uid = _make_user(client, admin)
    marked = client.delete(f"/api/admin/users/{uid}", headers=_bearer(admin)).json()

    notes = _history(uid)
    assert len(notes) == 1
    due = str(marked["deletion_due_at"])[:10]
    assert due in str(notes[0]["body"]), "the reversible window is the whole point of the note"
