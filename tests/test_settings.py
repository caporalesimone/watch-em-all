"""Tests for system settings defaults (4.B5)."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from src.core.db import Base
from src.core.settings import get_system_settings


def test_defaults_when_no_overrides() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        settings = get_system_settings(session)
    assert settings.scraper_run_timeout_min == 30
    assert settings.log_retention_days == 90
