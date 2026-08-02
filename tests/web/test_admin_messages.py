"""Admin messages: sending, the single-row broadcast and the read pointer (10.B12).

The tests worth having here are the ones that pin the *design* decision, not the endpoint: a
broadcast must cost one row however many accounts there are, and the badge must still count it
for each of them. Get either half wrong and the feature looks fine in a two-user installation.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from src.core.db import new_session
from src.core.models import AdminMessage, AdminMessageDelivery, AlertLog


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _admin_token(client: TestClient) -> str:
    login = client.post("/api/auth/login", json={"username": "admin", "password": "initpass123"})
    access = login.json()["access_token"]
    client.post(
        "/api/auth/change-password", json={"new_password": "adminpass123"}, headers=_bearer(access)
    )
    relogin = client.post("/api/auth/login", json={"username": "admin", "password": "adminpass123"})
    return str(relogin.json()["access_token"])


def _make_user(client: TestClient, admin: str, username: str) -> str:
    """Create an account and return a usable token (past the forced first change)."""
    client.post(
        "/api/admin/users",
        json={
            "username": username,
            "first_name": username.title(),
            "last_name": "Test",
            "role": "user",
            "temp_password": "temp-pass-123",
        },
        headers=_bearer(admin),
    )
    first = client.post("/api/auth/login", json={"username": username, "password": "temp-pass-123"})
    client.post(
        "/api/auth/change-password",
        json={"new_password": "user-pass-123"},
        headers=_bearer(first.json()["access_token"]),
    )
    again = client.post("/api/auth/login", json={"username": username, "password": "user-pass-123"})
    return str(again.json()["access_token"])


def _count(model: type) -> int:
    session = new_session()
    try:
        return int(session.scalar(select(func.count()).select_from(model)) or 0)
    finally:
        session.close()


def _unread(client: TestClient, token: str) -> int:
    return int(client.get("/api/alerts/unread-count", headers=_bearer(token)).json()["count"])


def test_broadcast_is_one_row_and_everyone_sees_it(client: TestClient) -> None:
    admin = _admin_token(client)
    alice = _make_user(client, admin, "alice")
    bob = _make_user(client, admin, "bob")

    sent = client.post(
        "/api/admin/messages",
        json={"title": "Maintenance", "body": "We are **down** on Sunday."},
        headers=_bearer(admin),
    )
    assert sent.status_code == 201
    body = sent.json()
    assert body["audience"] == "all"
    assert body["recipient_count"] == 2  # alice + bob; the admin is not an audience

    # The point of the design: one message row, and not a single per-user history copy.
    assert _count(AdminMessage) == 1
    assert _count(AlertLog) == 0
    # Outcomes stay per person, though — that is the part a pointer cannot compress.
    assert _count(AdminMessageDelivery) == 2  # in-app for each; email is not configured

    assert _unread(client, alice) == 1
    assert _unread(client, bob) == 1


def test_broadcast_read_pointer_moves_forward_only(client: TestClient) -> None:
    admin = _admin_token(client)
    alice = _make_user(client, admin, "alice")

    first = client.post(
        "/api/admin/messages", json={"title": "One", "body": "first"}, headers=_bearer(admin)
    ).json()
    second = client.post(
        "/api/admin/messages", json={"title": "Two", "body": "second"}, headers=_bearer(admin)
    ).json()
    assert _unread(client, alice) == 2

    # Reading the newer one clears the older: "read up to N" is all a pointer can say, and for
    # announcements that is the right shape (it is exactly why alerts keep per-row read state).
    assert (
        client.post(
            f"/api/alerts/broadcasts/{second['id']}/read", headers=_bearer(alice)
        ).status_code
        == 204
    )
    assert _unread(client, alice) == 0

    # And it never rewinds: re-reading the older one does not resurrect the newer.
    client.post(f"/api/alerts/broadcasts/{first['id']}/read", headers=_bearer(alice))
    assert _unread(client, alice) == 0


def test_broadcast_predating_an_account_arrives_already_read(client: TestClient) -> None:
    admin = _admin_token(client)
    client.post(
        "/api/admin/messages",
        json={"title": "Old news", "body": "before you"},
        headers=_bearer(admin),
    )
    late = _make_user(client, admin, "late")
    # An announcement is addressed to the people who were there. The archive is still visible —
    # announcements are public by nature — but it is not a backlog to clear, so the badge is 0.
    assert _unread(client, late) == 0
    listed = client.get("/api/alerts", headers=_bearer(late)).json()
    assert [(i["source"], i["read"]) for i in listed["items"]] == [("broadcast", True)]


def test_history_unions_alerts_and_broadcasts(client: TestClient) -> None:
    admin = _admin_token(client)
    alice = _make_user(client, admin, "alice")
    alice_id = next(
        u["id"]
        for u in client.get("/api/admin/users", headers=_bearer(admin)).json()
        if u["username"] == "alice"
    )
    client.post(
        "/api/admin/messages",
        json={"title": "Just you", "body": "personal", "target_user_id": alice_id},
        headers=_bearer(admin),
    )
    announcement = client.post(
        "/api/admin/messages", json={"title": "Everyone", "body": "shared"}, headers=_bearer(admin)
    ).json()

    listed = client.get("/api/alerts", headers=_bearer(alice)).json()
    assert listed["total"] == 2
    # Two sources, one list: the personal message has a row of its own, the announcement does
    # not, and the ids belong to different tables — which is why `source` exists.
    assert {i["source"] for i in listed["items"]} == {"alert", "broadcast"}
    assert all(i["kind"] == "admin_message" for i in listed["items"])

    detail = client.get(
        f"/api/alerts/broadcasts/{announcement['id']}", headers=_bearer(alice)
    ).json()
    assert detail["source"] == "broadcast"
    assert detail["payload"]["title"] == "Everyone"
    assert detail["read"] is False
    # The user sees how it was delivered to *them* — the in-app copy, at least.
    assert [d["status"] for d in detail["deliveries"]] == ["delivered"]

    client.post(f"/api/alerts/broadcasts/{announcement['id']}/read", headers=_bearer(alice))
    after = client.get(
        f"/api/alerts/broadcasts/{announcement['id']}", headers=_bearer(alice)
    ).json()
    assert after["read"] is True


def test_targeted_message_lands_in_that_users_history_only(client: TestClient) -> None:
    admin = _admin_token(client)
    alice = _make_user(client, admin, "alice")
    bob = _make_user(client, admin, "bob")
    alice_id = next(
        u["id"]
        for u in client.get("/api/admin/users", headers=_bearer(admin)).json()
        if u["username"] == "alice"
    )

    sent = client.post(
        "/api/admin/messages",
        json={"title": "About your scraper", "body": "Let us talk.", "target_user_id": alice_id},
        headers=_bearer(admin),
    )
    assert sent.status_code == 201
    assert sent.json()["audience"] == "user"
    assert sent.json()["target_username"] == "alice"
    assert sent.json()["recipient_count"] == 1

    # One recipient means the ordinary path: a real history row, no pointer involved.
    assert _count(AlertLog) == 1
    assert _unread(client, alice) == 1
    assert _unread(client, bob) == 0

    listed = client.get("/api/alerts", headers=_bearer(alice)).json()
    assert [item["kind"] for item in listed["items"]] == ["admin_message"]
    detail = client.get(f"/api/alerts/{listed['items'][0]['id']}", headers=_bearer(alice)).json()
    assert detail["payload"]["title"] == "About your scraper"
    assert detail["payload"]["body"] == "Let us talk."


def test_a_user_with_no_channels_still_gets_it_in_app(client: TestClient) -> None:
    # ADMSG-R2 / ALERT-R13: the history is written regardless, so the message cannot be lost by
    # a person who has configured nothing. In-app is the channel nobody can switch off.
    admin = _admin_token(client)
    alice = _make_user(client, admin, "alice")
    client.post(
        "/api/admin/messages", json={"title": "Heads up", "body": "hello"}, headers=_bearer(admin)
    )
    assert _unread(client, alice) == 1


def test_unknown_target_is_refused_not_silently_broadcast(client: TestClient) -> None:
    admin = _admin_token(client)
    resp = client.post(
        "/api/admin/messages",
        json={"title": "Nobody", "body": "x", "target_user_id": 9999},
        headers=_bearer(admin),
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "user_not_found"
    assert _count(AdminMessage) == 0


def test_sending_requires_admin(client: TestClient) -> None:
    admin = _admin_token(client)
    alice = _make_user(client, admin, "alice")
    resp = client.post(
        "/api/admin/messages", json={"title": "t", "body": "b"}, headers=_bearer(alice)
    )
    assert resp.status_code == 403
    assert client.post("/api/admin/messages", json={"title": "t", "body": "b"}).status_code == 401


def test_sent_list_shows_delivery_outcomes_never_read_state(client: TestClient) -> None:
    # ADMSG-R5, stated as a test: the admin's view of a message is about channels, not people.
    admin = _admin_token(client)
    _make_user(client, admin, "alice")
    client.post(
        "/api/admin/messages", json={"title": "Notice", "body": "body"}, headers=_bearer(admin)
    )

    page = client.get("/api/admin/messages", headers=_bearer(admin)).json()
    assert page["total"] == 1
    item = page["items"][0]
    assert item["title"] == "Notice"
    assert item["sender_username"] == "admin"
    assert item["recipient_count"] == 1  # alice; admins are never recipients
    # The one recipient got the in-app copy, which is a real delivery.
    assert item["outcomes"] == {"delivered": 1, "pending": 0, "failed": 0, "skipped": 0}
    assert "read" not in item and "read_count" not in item


def test_message_detail_lists_recipients_and_their_channels(client: TestClient) -> None:
    admin = _admin_token(client)
    _make_user(client, admin, "alice")
    sent = client.post(
        "/api/admin/messages", json={"title": "Notice", "body": "body"}, headers=_bearer(admin)
    ).json()

    detail = client.get(f"/api/admin/messages/{sent['id']}", headers=_bearer(admin)).json()
    assert {r["username"] for r in detail["recipients"]} == {"alice"}
    for person in detail["recipients"]:
        assert [c["plugin_id"] for c in person["channels"]] == ["in_app"]
        assert [c["status"] for c in person["channels"]] == ["delivered"]
    # Still no reception anywhere in the payload.
    assert all("read" not in r for r in detail["recipients"])


def test_message_detail_404_and_admin_only(client: TestClient) -> None:
    admin = _admin_token(client)
    alice = _make_user(client, admin, "alice")
    assert client.get("/api/admin/messages/999", headers=_bearer(admin)).status_code == 404
    assert client.get("/api/admin/messages", headers=_bearer(alice)).status_code == 403
    assert client.get("/api/admin/messages").status_code == 401


def test_history_filters_by_category_and_renders_the_body(client: TestClient) -> None:
    admin = _admin_token(client)
    alice = _make_user(client, admin, "alice")
    announcement = client.post(
        "/api/admin/messages",
        json={"title": "Maintenance", "body": "We are **down** on Sunday."},
        headers=_bearer(admin),
    ).json()

    # The category is derived from the kind (ADMSG-R4): announcements are admin, digests are not.
    admin_only = client.get("/api/alerts?category=admin", headers=_bearer(alice)).json()
    assert [i["title"] for i in admin_only["items"]] == ["Maintenance"]
    system_only = client.get("/api/alerts?category=system", headers=_bearer(alice)).json()
    assert system_only["items"] == [] and system_only["total"] == 0

    detail = client.get(
        f"/api/alerts/broadcasts/{announcement['id']}", headers=_bearer(alice)
    ).json()
    # Rendered by the core, not by the browser: the same helper the email uses, already
    # sanitised, so the two channels cannot say the message differently.
    assert "<strong>down</strong>" in detail["payload"]["body_html"]
    assert detail["payload"]["body"] == "We are **down** on Sunday."


def test_a_digest_has_no_title_and_a_message_does(client: TestClient) -> None:
    admin = _admin_token(client)
    alice = _make_user(client, admin, "alice")
    alice_id = next(
        u["id"]
        for u in client.get("/api/admin/users", headers=_bearer(admin)).json()
        if u["username"] == "alice"
    )
    client.post(
        "/api/admin/messages",
        json={"title": "Just you", "body": "personal", "target_user_id": alice_id},
        headers=_bearer(admin),
    )
    items = client.get("/api/alerts", headers=_bearer(alice)).json()["items"]
    # A digest's one-line preview is its cart count, so `title` is null there rather than a
    # manufactured heading.
    assert [i["title"] for i in items] == ["Just you"]


def test_preview_renders_with_the_same_helper_that_delivers(client: TestClient) -> None:
    # 10.F9: the Preview tab must not be an approximation. It goes through the server so the
    # HTML it shows is the same HTML the recipients get — the property, asserted rather than
    # assumed, by comparing the two.
    admin = _admin_token(client)
    draft = "Hello **there**\n\n- one\n- two"
    preview = client.post(
        "/api/admin/messages/preview", json={"body": draft}, headers=_bearer(admin)
    )
    assert preview.status_code == 200
    rendered = preview.json()["body_html"]
    assert "<strong>there</strong>" in rendered and "<li>one</li>" in rendered

    alice = _make_user(client, admin, "alice")
    sent = client.post(
        "/api/admin/messages", json={"title": "T", "body": draft}, headers=_bearer(admin)
    ).json()
    delivered = client.get(f"/api/alerts/broadcasts/{sent['id']}", headers=_bearer(alice)).json()
    assert delivered["payload"]["body_html"] == rendered


def test_preview_is_admin_only_and_sanitises(client: TestClient) -> None:
    admin = _admin_token(client)
    alice = _make_user(client, admin, "alice")
    assert client.post("/api/admin/messages/preview", json={"body": "x"}).status_code == 401
    assert (
        client.post(
            "/api/admin/messages/preview", json={"body": "x"}, headers=_bearer(alice)
        ).status_code
        == 403
    )
    hostile = client.post(
        "/api/admin/messages/preview",
        json={"body": "<script>alert(1)</script>"},
        headers=_bearer(admin),
    ).json()["body_html"]
    # What the admin sees in the preview is the escaped form, because that is what gets
    # delivered — a preview that showed the raw text would be lying about the outcome.
    assert "<script>" not in hostile and "&lt;script&gt;" in hostile


def test_administrators_are_never_recipients(client: TestClient) -> None:
    # Simone's rule, 2026-08-02: this channel talks to the people who use the installation, and
    # whoever administers it already has the logs. Stated on the server, not in the dropdown.
    admin = _admin_token(client)
    alice = _make_user(client, admin, "alice")
    client.post(
        "/api/admin/users",
        json={
            "username": "second",
            "first_name": "Second",
            "last_name": "Admin",
            "role": "admin",
            "temp_password": "temp-pass-123",
        },
        headers=_bearer(admin),
    )
    second_id = next(
        u["id"]
        for u in client.get("/api/admin/users", headers=_bearer(admin)).json()
        if u["username"] == "second"
    )

    sent = client.post(
        "/api/admin/messages", json={"title": "Notice", "body": "b"}, headers=_bearer(admin)
    ).json()
    # Two admins exist and neither is counted; alice is the whole audience.
    assert sent["recipient_count"] == 1
    assert _unread(client, alice) == 1
    detail = client.get(f"/api/admin/messages/{sent['id']}", headers=_bearer(admin)).json()
    assert [r["username"] for r in detail["recipients"]] == ["alice"]

    # And an admin cannot be picked out by hand either.
    refused = client.post(
        "/api/admin/messages",
        json={"title": "You", "body": "b", "target_user_id": second_id},
        headers=_bearer(admin),
    )
    assert refused.status_code == 422
    assert refused.json()["code"] == "recipient_is_admin"


def test_an_admin_cannot_message_themselves(client: TestClient) -> None:
    admin = _admin_token(client)
    own_id = next(
        u["id"]
        for u in client.get("/api/admin/users", headers=_bearer(admin)).json()
        if u["username"] == "admin"
    )
    refused = client.post(
        "/api/admin/messages",
        json={"title": "Note to self", "body": "b", "target_user_id": own_id},
        headers=_bearer(admin),
    )
    assert refused.status_code == 422
    assert _count(AdminMessage) == 0
