"""Unit tests for the schema-drift guard (4.B0)."""

from __future__ import annotations

from sqlalchemy import Column, Engine, Integer, MetaData, String, Table, create_engine
from sqlalchemy.pool import StaticPool

from src.core.schema_drift import check_schema_drift


def _engine() -> Engine:
    # One shared in-memory connection so create_all and inspect see the same DB.
    return create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def test_no_drift_when_db_matches_model() -> None:
    engine = _engine()
    md = MetaData()
    Table("widget", md, Column("id", Integer, primary_key=True), Column("name", String(32)))
    md.create_all(engine)
    assert check_schema_drift(engine, [md]) == []


def test_missing_column_is_reported() -> None:
    engine = _engine()
    # The DB has `widget` with only `id`; the model adds a `name` column.
    db_md = MetaData()
    Table("widget", db_md, Column("id", Integer, primary_key=True))
    db_md.create_all(engine)

    model_md = MetaData()
    Table("widget", model_md, Column("id", Integer, primary_key=True), Column("name", String(32)))

    drift = check_schema_drift(engine, [model_md])
    assert len(drift) == 1
    assert drift[0].table == "widget"
    assert drift[0].missing_table is False
    assert drift[0].missing_columns == ["name"]


def test_missing_table_is_reported() -> None:
    engine = _engine()  # empty DB
    model_md = MetaData()
    Table("ghost", model_md, Column("id", Integer, primary_key=True))

    drift = check_schema_drift(engine, [model_md])
    assert len(drift) == 1
    assert drift[0].table == "ghost"
    assert drift[0].missing_table is True
    assert drift[0].missing_columns == []
