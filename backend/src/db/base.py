"""SQLAlchemy declarative base and reusable mixins; no domain tables here."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata_obj = MetaData(naming_convention=NAMING_CONVENTION)


class Base(DeclarativeBase):
    """Declarative base for every ORM model in the project."""

    metadata = metadata_obj


class TimestampMixin:
    """Mixin providing audit timestamp columns.

    Both columns use the database `now()` server default so values are
    populated even when rows are inserted via raw SQL or Alembic migrations.
    `updated_at` uses ``onupdate=func.now()`` for ORM-driven updates; raw SQL
    updates that need to bump the timestamp must include it explicitly.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ReprMixin:
    """Mixin that produces a compact ``repr`` for ORM rows."""

    def __repr__(self) -> str:  # pragma: no cover - trivial formatter
        cls = type(self).__name__
        try:
            mapper = self.__mapper__  # type: ignore[attr-defined]
        except AttributeError:
            return f"<{cls}>"
        pk_attrs = [col.key for col in mapper.primary_key]
        pk_repr = ", ".join(f"{name}={getattr(self, name, None)!r}" for name in pk_attrs)
        return f"<{cls}({pk_repr})>"


__all__ = ["NAMING_CONVENTION", "Base", "ReprMixin", "TimestampMixin", "metadata_obj"]
