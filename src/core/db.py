"""Database engine, session factory and idempotent schema creation.

Synchronous SQLAlchemy (BE-21): a classic Session, psycopg in sync mode. The
schema is created idempotently at startup by web and worker (DB-R4: additive
`create_all`, never drop & recreate).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def init_engine(database_url: str) -> Engine:
    """Create the process-wide engine and session factory.

    The production URL is PostgreSQL; the only special-casing is for SQLite,
    which the test suite uses in-memory — it needs a single shared connection
    (StaticPool) across the threadpool, with check_same_thread disabled.
    """
    global _engine, _session_factory
    kwargs: dict[str, Any] = {"pool_pre_ping": True, "future": True}
    if database_url.startswith("sqlite"):
        kwargs = {"future": True, "connect_args": {"check_same_thread": False, "timeout": 10}}
        if ":memory:" in database_url:
            # An in-memory database exists **per connection**, so the whole process has to
            # share one (StaticPool). The catch, and it bit us in 9.X6c: sessions on one
            # connection also share one transaction, so a background thread's rollback
            # discards the request's uncommitted work. Tests that exercise concurrency use a
            # file-backed SQLite instead, which gives each connection its own — the way
            # PostgreSQL behaves in production.
            kwargs["poolclass"] = StaticPool
    _engine = create_engine(database_url, **kwargs)
    if database_url.startswith("sqlite"):
        # SQLite ignores ON DELETE CASCADE unless foreign keys are switched on per connection,
        # and it is off by default. Without this the test database quietly disagrees with
        # production about what deleting a product does to its price history and its cart
        # memberships (9.B7) — the tests would pass and the real cascade would be untested.
        @event.listens_for(_engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection: Any, _record: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    _session_factory = sessionmaker(
        bind=_engine, autoflush=False, expire_on_commit=False, future=True
    )
    return _engine


def get_engine() -> Engine:
    if _engine is None:
        raise RuntimeError("engine not initialised; call init_engine() first")
    return _engine


def new_session() -> Session:
    if _session_factory is None:
        raise RuntimeError("session factory not initialised; call init_engine() first")
    return _session_factory()


def create_schema() -> None:
    """Create any missing tables. Idempotent (DB-R4)."""
    # Import models for the side effect of registering them on Base.metadata.
    from src.core import models  # noqa: F401

    Base.metadata.create_all(get_engine())


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session."""
    session = new_session()
    try:
        yield session
    finally:
        session.close()
