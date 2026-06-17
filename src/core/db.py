"""Database engine, session factory and idempotent schema creation.

Synchronous SQLAlchemy (BE-21): a classic Session, psycopg in sync mode. The
schema is created idempotently at startup by web and worker (DB-R4: additive
`create_all`, never drop & recreate).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from sqlalchemy import Engine, create_engine
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
        kwargs = {
            "future": True,
            "connect_args": {"check_same_thread": False},
            "poolclass": StaticPool,
        }
    _engine = create_engine(database_url, **kwargs)
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
