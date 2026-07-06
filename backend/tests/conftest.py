"""Shared pytest fixtures for the API test suite.

The API route handlers depend on ``get_db`` which would otherwise open a
real PostgreSQL connection. For unit tests we override that dependency
with an inert stub; individual tests monkeypatch the private ``_fetch_*``
query functions to return canned rows
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from src.db.session import get_db
from src.main import app


class _InertSession:
    """Stand-in for a SQLAlchemy ``Session`` that does nothing.

    Route handlers receive this via ``Depends(get_db)`` but never use it
    directly; the actual query functions are monkeypatched in each test
    """

    def execute(self, *args, **kwargs):  # pragma: no cover - never invoked
        raise AssertionError(
            "Inert test session must never have execute() called; "
            "monkeypatch the route's _fetch_* helper instead."
        )

    def close(self) -> None:  # pragma: no cover
        pass


def _override_get_db() -> Iterator[_InertSession]:
    session = _InertSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def _override_db_dependency() -> Iterator[None]:
    """Replace ``get_db`` for every API test, restore afterwards"""
    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db, None)
