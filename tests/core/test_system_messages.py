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


# ------------------------------------------------------------------------ the admin API (10.B17)


def test_the_list_is_the_catalog_not_the_table(client: TestClient) -> None:
    """ADMSG-R9 from the outside: every key shows up with nothing stored anywhere."""
    admin = _admin(client)
    items = client.get("/api/admin/message-templates", headers=_bearer(admin)).json()
    assert {i["key"] for i in items} == set(sysmsg.CATALOG)
    assert all(i["is_override"] is False for i in items)
    disabled = next(i for i in items if i["key"] == "user.disabled")
    assert disabled["title"] == disabled["default_title"]
    assert "deletion_due_date" not in disabled["placeholders"]


def test_an_override_round_trips_and_a_delete_returns_the_default(client: TestClient) -> None:
    admin = _admin(client)
    saved = client.put(
        "/api/admin/message-templates/user.disabled",
        json={"title": "Closed", "body": "Sorry {first_name}."},
        headers=_bearer(admin),
    )
    assert saved.status_code == 200
    assert saved.json()["is_override"] is True

    back = client.delete("/api/admin/message-templates/user.disabled", headers=_bearer(admin))
    assert back.status_code == 204
    after = client.get("/api/admin/message-templates", headers=_bearer(admin)).json()
    entry = next(i for i in after if i["key"] == "user.disabled")
    assert entry["is_override"] is False and entry["title"] == sysmsg.USER_DISABLED.title


def test_an_unknown_placeholder_is_a_warning_a_missing_one_is_a_refusal(
    client: TestClient,
) -> None:
    admin = _admin(client)
    # Untidy, but it degrades to literal text — so it is saved, and reported.
    warned = client.put(
        "/api/admin/message-templates/user.disabled",
        json={"title": "T", "body": "Bye {usernme}"},
        headers=_bearer(admin),
    ).json()
    assert warned["is_override"] is True
    assert warned["unknown_placeholders"] == ["usernme"]

    # A credential mail without the credential is not saved at all.
    refused = client.put(
        "/api/admin/message-templates/user.credentials.reset",
        json={"title": "T", "body": "Your password was reset."},
        headers=_bearer(admin),
    )
    assert refused.status_code == 422
    assert refused.json()["code"] == "missing_placeholder"
    still_default = client.get("/api/admin/message-templates", headers=_bearer(admin)).json()
    entry = next(i for i in still_default if i["key"] == "user.credentials.reset")
    assert entry["is_override"] is False


def test_a_key_the_core_does_not_declare_is_refused(client: TestClient) -> None:
    admin = _admin(client)
    resp = client.put(
        "/api/admin/message-templates/made.up.key",
        json={"title": "T", "body": "B"},
        headers=_bearer(admin),
    )
    assert resp.status_code == 404


def test_the_override_is_what_actually_gets_delivered(client: TestClient) -> None:
    """The point of the endpoint: the text an admin saves is the text the person receives."""
    admin = _admin(client)
    client.put(
        "/api/admin/message-templates/user.disabled",
        json={"title": "Access closed", "body": "Sorry {first_name}, ask the office."},
        headers=_bearer(admin),
    )
    uid = _make_user(client, admin)
    client.patch(f"/api/admin/users/{uid}", json={"is_active": False}, headers=_bearer(admin))
    note = _history(uid)[0]
    assert note["title"] == "Access closed"
    assert note["body"] == "Sorry Alice, ask the office."
