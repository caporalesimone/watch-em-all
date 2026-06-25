"""Schema-drift guard (4.B0).

Compares the ORM model (SQLAlchemy ``MetaData``) against the live database via
``inspect``, run at startup AFTER the schema is ensured (``create_schema`` + each
plugin's ``initialize``). It catches the case ``create_all`` cannot fix: a COLUMN
added to a model whose table already exists in an existing DB — ``create_all`` only
creates missing tables, it never alters existing ones — which otherwise surfaces as
a 500 at query time (the real phase-3 incidents: ``products.brand/tags`` and
``plugin_dragon_store_watches.name``). Missing whole tables are reported too
(defensive). Column types, nullability and indexes are out of scope: this is a
drift alarm, not a migration tool.

It covers the core (``Base.metadata``) and every plugin that declares its own
``table_metadata`` (DB-R7). Pure and side-effect free: the caller logs the findings
and decides what to expose (the web surfaces them on ``/api/health`` behind
``WEA_SCHEMA_DRIFT_ALERT``).
"""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel
from sqlalchemy import Engine, MetaData, inspect


class SchemaDriftItem(BaseModel):
    """One drift finding: a table missing entirely, or a table missing some columns."""

    table: str
    missing_table: bool = False
    missing_columns: list[str] = []


def check_schema_drift(engine: Engine, metadatas: Iterable[MetaData]) -> list[SchemaDriftItem]:
    """Return the drift between the ORM ``metadatas`` and the live DB at ``engine``.

    For each table declared in the metadata: if it is absent from the DB → a
    ``missing_table`` item; otherwise the model columns absent from the DB table →
    a ``missing_columns`` item. Raises only if the database cannot be inspected at
    all — the caller wraps the call so a check failure never blocks startup.
    """
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    items: list[SchemaDriftItem] = []
    for metadata in metadatas:
        for name, table in metadata.tables.items():
            if name not in existing:
                items.append(SchemaDriftItem(table=name, missing_table=True))
                continue
            db_columns = {column["name"] for column in inspector.get_columns(name)}
            missing = [col.name for col in table.columns if col.name not in db_columns]
            if missing:
                items.append(SchemaDriftItem(table=name, missing_columns=missing))
    return items
