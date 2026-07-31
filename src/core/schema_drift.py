"""Schema-drift guard (4.B0).

Compares the ORM model (SQLAlchemy ``MetaData``) against the live database via
``inspect``, run at startup AFTER the schema is ensured (``create_schema`` + each
plugin's ``initialize``). It catches what ``create_all`` cannot fix, because
``create_all`` only creates missing tables and never alters existing ones:

- a **column added** to a model whose table already exists (the real phase-3
  incidents: ``products.brand/tags`` and ``plugin_dragon_store_watches.name``);
- a **table missing** entirely (defensive);
- a **column removed** from a model that the database still requires — ``NOT NULL``
  with no default, so an INSERT that no longer mentions it is rejected. This is the
  mirror image of the first case and the guard used to be blind to it: on a 0.8.0
  database, 0.9.0 reported the missing ``price_history`` columns and said nothing
  about the leftover ``NOT NULL`` columns that break adding a watch.

An extra column the database does *not* require is **not** reported. A nullable
leftover, or one with a server default, costs nothing: it sits there unread. Only
what actually stops the application from working belongs here, because everything
reported is treated as an incompatibility (INC-R1) rather than a remark.

Column types, nullability of *model* columns and indexes stay out of scope: this is
a drift alarm, not a migration tool.

It covers the core (``Base.metadata``) and every plugin that declares its own
``table_metadata`` (DB-R7). Pure and side-effect free: the caller logs the findings
and decides what to do with them — the web serves the incompatibility page
(:mod:`src.web.incompatible`), the worker holds off its scheduled work.
"""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel
from sqlalchemy import Engine, MetaData, inspect


class SchemaDriftItem(BaseModel):
    """One drift finding on one table. Every finding means the application cannot work
    against this database as it stands."""

    table: str
    missing_table: bool = False
    # In the model, absent from the database: reads and writes of them fail.
    missing_columns: list[str] = []
    # In the database and required by it (NOT NULL, no default), absent from the model:
    # every INSERT is rejected, because the model no longer supplies a value.
    unexpected_required_columns: list[str] = []

    def summary(self) -> str:
        """One line, for a log or the page. The three cases read differently on purpose:
        an operator needs to know whether something is missing or left over."""
        if self.missing_table:
            return f"table {self.table!r} is missing from the database"
        parts = []
        if self.missing_columns:
            parts.append(f"is missing column(s): {', '.join(self.missing_columns)}")
        if self.unexpected_required_columns:
            parts.append(
                "still requires column(s) the application no longer writes: "
                f"{', '.join(self.unexpected_required_columns)}"
            )
        return f"table {self.table!r} " + " and ".join(parts)


def check_schema_drift(engine: Engine, metadatas: Iterable[MetaData]) -> list[SchemaDriftItem]:
    """Return the drift between the ORM ``metadatas`` and the live DB at ``engine``.

    For each table declared in the metadata: absent from the DB → a ``missing_table``
    item; otherwise the model columns absent from the DB, plus the DB columns the DB
    *requires* and the model does not declare. Raises only if the database cannot be
    inspected at all — the caller wraps the call so a check failure never blocks startup.
    """
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    items: list[SchemaDriftItem] = []
    for metadata in metadatas:
        for name, table in metadata.tables.items():
            if name not in existing:
                items.append(SchemaDriftItem(table=name, missing_table=True))
                continue
            db_columns = {column["name"]: column for column in inspector.get_columns(name)}
            model_columns = {col.name for col in table.columns}
            missing = [col.name for col in table.columns if col.name not in db_columns]
            unexpected_required = [
                col_name
                for col_name, column in db_columns.items()
                if col_name not in model_columns
                and not column.get("nullable", True)
                and column.get("default") is None
                and not column.get("autoincrement", False)
            ]
            if missing or unexpected_required:
                items.append(
                    SchemaDriftItem(
                        table=name,
                        missing_columns=missing,
                        unexpected_required_columns=unexpected_required,
                    )
                )
    return items
