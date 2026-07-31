"""The database-incompatibility page and the drift that triggers it (INC-R1..R4, 4.B0).

Two halves, and the second is the one that matters: the guard has to *see* the mismatch a
new version actually produces. The scenario is the real one — 0.9.0's code against a 0.8.0
database — reproduced by making the live schema disagree with the model in both directions:
a column the model wants and the DB lacks, and a column the DB requires and the model no
longer writes. The second used to go unnoticed, and it is the one that breaks writes.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from src.core.db import create_schema, get_engine, init_engine
from src.core.schema_drift import SchemaDriftItem, check_schema_drift
from src.web.incompatible import render_page

# --------------------------------------------------------------- what the guard sees


@pytest.fixture()
def engine_with_schema(tmp_path: object) -> Iterator[None]:
    init_engine(f"sqlite+pysqlite:///{tmp_path}/drift.db")
    create_schema()
    yield


def _drift_of(sql: str | None = None) -> list[SchemaDriftItem]:
    """The drift of the core model against the live DB, after optionally altering it."""
    from src.core.db import Base

    if sql is not None:
        with get_engine().begin() as conn:
            conn.execute(text(sql))
    return check_schema_drift(get_engine(), [Base.metadata])


def test_a_matching_database_has_no_drift(engine_with_schema: None) -> None:
    assert _drift_of() == []


def test_a_missing_table_is_reported(engine_with_schema: None) -> None:
    drift = _drift_of("DROP TABLE price_history")

    (item,) = [d for d in drift if d.table == "price_history"]
    assert item.missing_table is True
    assert "is missing from the database" in item.summary()


def test_a_column_the_model_wants_and_the_database_lacks_is_reported(
    engine_with_schema: None,
) -> None:
    """The original case (phase 3): `create_all` never alters an existing table, so a column
    added to a model is simply absent until the database is recreated."""
    drift = _drift_of("ALTER TABLE products DROP COLUMN removed_at")

    (item,) = [d for d in drift if d.table == "products"]
    assert item.missing_columns == ["removed_at"]
    assert "is missing column(s): removed_at" in item.summary()


def test_a_column_the_database_requires_and_the_model_dropped_is_reported(
    engine_with_schema: None,
) -> None:
    """The mirror image, and the case the guard used to miss entirely. This is exactly what
    0.9.0 meets on a 0.8.0 database: `price_history.product_id` is still there, still NOT
    NULL, and the model no longer writes it — so every INSERT is rejected, while the guard
    reported only the *missing* columns and said nothing about this."""
    drift = _drift_of("ALTER TABLE products ADD COLUMN legacy_flag INTEGER NOT NULL DEFAULT 0")
    assert [d for d in drift if d.table == "products"] == []  # a default: the DB can fill it

    drift = _drift_of("ALTER TABLE carts ADD COLUMN legacy_required INTEGER NOT NULL")

    (item,) = [d for d in drift if d.table == "carts"]
    assert item.unexpected_required_columns == ["legacy_required"]
    assert "no longer writes" in item.summary()


def test_a_harmless_leftover_column_is_not_reported(engine_with_schema: None) -> None:
    """A nullable leftover costs nothing — it sits there unread. Reporting it would take the
    whole application down for something that breaks nothing, and everything reported here is
    treated as an incompatibility rather than a remark."""
    drift = _drift_of("ALTER TABLE carts ADD COLUMN legacy_note VARCHAR(16)")

    assert [d for d in drift if d.table == "carts"] == []


# --------------------------------------------------------------- what the user sees

_FINDINGS = [
    SchemaDriftItem(table="price_history", missing_columns=["plugin_id", "external_id"]),
    SchemaDriftItem(
        table="plugin_dragon_store_watches", unexpected_required_columns=["progress_done"]
    ),
]


def test_the_page_names_the_tables_and_the_version() -> None:
    html = render_page(_FINDINGS, "0.9.0")

    assert "price_history" in html and "plugin_id, external_id" in html
    assert "plugin_dragon_store_watches" in html and "progress_done" in html
    assert "0.9.0" in html
    assert "down -v" in html  # the remedy, not just the diagnosis


def test_the_page_escapes_what_it_did_not_write() -> None:
    """Table and column names come from a database this process does not control."""
    html = render_page([SchemaDriftItem(table="<script>x</script>", missing_table=True)], "1.0")

    assert "<script>x</script>" not in html
    assert "&lt;script&gt;" in html


def test_every_page_and_api_route_answers_the_incompatibility(client: TestClient) -> None:
    """The point of the page: one legible cause instead of 500s from whichever route touches
    the wrong table first. The SPA gets HTML, a script gets JSON it can read."""
    app = cast(FastAPI, client.app)
    app.state.schema_drift = _FINDINGS
    try:
        page = client.get("/")
        api = client.get("/api/catalog")
        health = client.get("/api/health")
    finally:
        app.state.schema_drift = []

    assert page.status_code == 503
    assert "database does not match" in page.text
    assert api.status_code == 503
    assert api.json()["code"] == "schema_incompatible"
    assert api.json()["findings"]  # says which tables, not just that something is wrong
    # Health stays reachable on purpose: it is what a monitor polls and what an operator
    # curls, and blocking it would turn a legible failure into an unreachable service.
    assert health.status_code == 200


def test_nothing_is_blocked_when_the_schema_matches(client: TestClient) -> None:
    """The normal case, asserted so the gate cannot quietly start blocking a healthy app."""
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/catalog").status_code == 401  # unauthenticated, not 503
