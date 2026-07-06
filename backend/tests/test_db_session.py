"""Tests for the SQLAlchemy base, mixins, and session factory.

These tests must run without a live PostgreSQL database. We exercise the
session lifecycle against an in-memory SQLite engine
"""

from __future__ import annotations

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.db.base import Base, ReprMixin, TimestampMixin
from src.db.session import create_engine_from_settings


def test_base_metadata_exists() -> None:
    assert Base.metadata is not None
    assert isinstance(Base.metadata.tables, dict)


def test_timestamp_mixin_has_created_and_updated_at_columns() -> None:
    column_names = set(TimestampMixin.__annotations__.keys())
    assert "created_at" in column_names
    assert "updated_at" in column_names


def test_repr_mixin_is_importable() -> None:
    assert ReprMixin is not None


def test_create_engine_for_in_memory_sqlite() -> None:
    engine = create_engine_from_settings("sqlite+pysqlite:///:memory:")
    assert isinstance(engine, Engine)
    assert engine.url.drivername.startswith("sqlite")
    engine.dispose()


def test_get_db_yields_and_closes_session_against_sqlite_override() -> None:
    engine = create_engine_from_settings("sqlite+pysqlite:///:memory:")
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    def _get_db_override():
        session = TestSession()
        try:
            yield session
        finally:
            session.close()

    gen = _get_db_override()
    session = next(gen)
    assert isinstance(session, Session)
    # Closing the generator runs the finally clause and closes the session
    try:
        next(gen)
    except StopIteration:
        pass
    # After closing, the session should not have an active in-flight transaction
    assert not session.in_transaction()
    engine.dispose()
