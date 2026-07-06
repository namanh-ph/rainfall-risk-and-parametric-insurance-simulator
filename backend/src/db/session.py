"""SQLAlchemy engine + session factory for the backend.

The engine is built lazily so importing this module does not open any
network connection. Tests can override the URL via
``create_engine_from_settings(url)`` or by constructing a fresh
``sessionmaker`` against a SQLite in-memory engine
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.core.config import get_settings


def create_engine_from_settings(database_url: str | None = None, **engine_kwargs: Any) -> Engine:
    """Build a SQLAlchemy engine.

    Defaults are tuned for local development: ``pool_pre_ping=True`` to drop
    stale connections after Postgres restarts, modest pool sizes suitable for
    a single backend container
    """
    url = database_url or get_settings().DATABASE_URL
    defaults: dict[str, Any] = {
        "pool_pre_ping": True,
        "future": True,
    }
    if url.startswith("sqlite"):
        # In-memory SQLite needs a single shared connection
        defaults["connect_args"] = {"check_same_thread": False}
    else:
        defaults["pool_size"] = 5
        defaults["max_overflow"] = 10
        defaults["pool_recycle"] = 1800
    defaults.update(engine_kwargs)
    return create_engine(url, **defaults)


# Module-level engine + sessionmaker bound to the configured DATABASE_URL
# These are created lazily via accessors so importing this module never
# triggers a connection attempt
_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def _get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine_from_settings()
    return _engine


def SessionLocal() -> Session:
    """Return a new ``Session`` bound to the application engine"""
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=_get_engine(),
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
            future=True,
        )
    return _session_factory()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a session and closes it after use"""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def reset_engine_for_tests() -> None:
    """Drop the cached engine + sessionmaker. Test-only helper"""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


__all__ = [
    "SessionLocal",
    "create_engine_from_settings",
    "get_db",
    "reset_engine_for_tests",
]
